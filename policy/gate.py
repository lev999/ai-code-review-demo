#!/usr/bin/env python3
"""Trusted, fail-closed policy gate for the two-list review demonstration.

The workflow checks out the pull request base revision. This program reads the
base and head as Git objects. It does not import or execute code from the head.

Trusted manifests:
  policy/required-tests.json:
    {"schema":1,"tests":[{"id":...,"path":...,"sha256":...}, ...]}
  policy/routine-patches.json:
    {"schema":1,"trusted_base":{"first_parent":...,"anchors":{path:sha256}},
     "patches":[{"id":...,"paths":[...sorted...],"sha256":...}]}

A bootstrap commit is the unique first-parent child of trusted_base.first_parent
whose anchor files match. This proves the H7 base without storing that commit's
own SHA inside its tree. Routine patches are valid only when that bootstrap
commit is still the live PR base.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

REPOSITORY = "lev999/ai-code-review-demo"
BASE_BRANCH = "main"
BOT_LOGIN = "github-actions[bot]"
BOT_USER_ID = 41898282
ACTIONS_APP_ID = 15368
POLICY_CONTEXT = "demo-policy"
CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
CI_JOB_NAME = "demo-tests"
REQUIRED_IDS = {
    "smoke-move": "tests/test_move.py",
    "smoke-preserve": "tests/test_preserve.py",
    "board-selection": "web/tests/task_state.test.js",
    "task-api": "api/tests/test_tasks_api.py",
    "browser-reload": "web/tests/e2e/test_board.mjs",
}
SUMMARY_FIELDS = (
    "Simulation case",
    "Rules added, changed, and removed (give IDs or write none)",
    "Old behavior",
    "New behavior",
    "Tests added",
    "Tests removed",
    "Relevant tests and runs",
    "Reviewer role",
)
CASES = {"feature": "H6", "routine": "H8", "judgment": "H9", "required-test removal": "H10"}
PROTECTED_PATHS = {
    "policy/gate.py",
    "policy/required-tests.json",
    "policy/routine-patches.json",
    ".github/workflows/policy.yml",
    ".github/workflows/ci.yml",
    ".github/pull_request_template.md",
    "Makefile",
    "web/package.json",
    "web/package-lock.json",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
URL_RE = re.compile(r"https://[^\s<>\])]+")


class GateError(Exception):
    pass


def fail(message: str) -> None:
    raise GateError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            fail("manifest contains a duplicate JSON key")
        value[key] = item
    return value


def parse_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail(f"{label} is not valid JSON")


def valid_sha(value: Any, size: int = 40) -> bool:
    return isinstance(value, str) and bool((SHA40 if size == 40 else SHA64).fullmatch(value))


def valid_repo_path(path: Any) -> bool:
    return (
        isinstance(path, str)
        and bool(path)
        and not path.startswith("/")
        and "\\" not in path
        and "\x00" not in path
        and all(part not in ("", ".", "..") for part in path.split("/"))
    )


def validate_required_manifest(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, dict) or set(value) != {"schema", "tests"} or value["schema"] != 1:
        fail("required-test manifest has an unknown schema")
    entries = value["tests"]
    if not isinstance(entries, list) or len(entries) != len(REQUIRED_IDS):
        fail("required-test manifest does not list the active test set")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    normalized: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"id", "path", "sha256"}:
            fail("required-test entry must have id, path, and sha256")
        test_id, path, digest = item["id"], item["path"], item["sha256"]
        if not isinstance(test_id, str) or test_id not in REQUIRED_IDS:
            fail("required-test manifest has an unknown test ID")
        if REQUIRED_IDS[test_id] != path:
            fail(f"required-test ID {test_id} has the wrong path")
        if test_id in seen_ids or path in seen_paths:
            fail("required-test IDs and paths must be unique")
        if not valid_repo_path(path) or not valid_sha(digest, 64):
            fail("required-test entry has an invalid path or SHA-256")
        seen_ids.add(test_id)
        seen_paths.add(path)
        normalized.append({"id": test_id, "path": path, "sha256": digest})
    if seen_ids != set(REQUIRED_IDS):
        fail("required-test manifest is missing a stable test ID")
    return sorted(normalized, key=lambda row: row["id"])


def validate_routine_manifest(value: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != {"schema", "trusted_base", "patches"} or value["schema"] != 1:
        fail("routine-patch manifest has an unknown schema")
    proof = value["trusted_base"]
    if not isinstance(proof, dict) or set(proof) != {"first_parent", "anchors"}:
        fail("routine manifest has an invalid trusted-base proof")
    if not valid_sha(proof["first_parent"]):
        fail("routine trusted-base first parent is not a full SHA")
    anchors = proof["anchors"]
    required_anchors = {
        "policy/gate.py",
        ".github/workflows/policy.yml",
        CI_WORKFLOW_PATH,
        "api/app.py",
        "policy/required-tests.json",
    }
    if not isinstance(anchors, dict) or not required_anchors.issubset(anchors):
        fail("routine trusted-base proof is missing required anchors")
    for path, digest in anchors.items():
        if not valid_repo_path(path) or path == "policy/routine-patches.json" or not valid_sha(digest, 64):
            fail("routine trusted-base proof has an invalid anchor")
    patches = value["patches"]
    if not isinstance(patches, list):
        fail("routine-patch list is invalid")
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for item in patches:
        if not isinstance(item, dict) or set(item) != {"id", "paths", "sha256"}:
            fail("routine patch entry must have id, paths, and sha256")
        patch_id, paths, digest = item["id"], item["paths"], item["sha256"]
        if not isinstance(patch_id, str) or not patch_id.strip() or patch_id in seen:
            fail("routine patch IDs must be non-empty and unique")
        if not isinstance(paths, list) or not paths or any(not valid_repo_path(path) for path in paths):
            fail("routine patch paths are invalid")
        if paths != sorted(set(paths)):
            fail("routine patch paths must be unique and sorted")
        if not valid_sha(digest, 64):
            fail("routine patch SHA-256 is invalid")
        seen.add(patch_id)
        clean.append({"id": patch_id, "paths": paths, "sha256": digest})
    return {"first_parent": proof["first_parent"], "anchors": anchors}, clean


class GitObjects:
    """Read Git objects and diffs without checking out or running head files."""

    def git(self, args: list[str], *, input_data: bytes | None = None, check: bool = True) -> bytes:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        result = subprocess.run(
            ["git", *args],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        if check and result.returncode:
            fail("required Git object or diff is unavailable")
        return result.stdout

    def fetch(self, revision: str) -> None:
        if not valid_sha(revision):
            fail("refusing to fetch a non-SHA revision")
        self.git(["fetch", "--no-tags", "origin", revision])

    def tree(self, revision: str) -> dict[str, tuple[str, str, str]]:
        if not valid_sha(revision):
            fail("Git tree revision is invalid")
        raw = self.git(["ls-tree", "-rz", "--full-tree", revision])
        entries: dict[str, tuple[str, str, str]] = {}
        for record in raw.split(b"\x00"):
            if not record:
                continue
            try:
                metadata, path_bytes = record.split(b"\t", 1)
                mode, kind, object_sha = metadata.decode("ascii").split(" ")
                path = path_bytes.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                fail("Git tree contains an unsupported path")
            if not valid_repo_path(path) or kind != "blob" or not valid_sha(object_sha):
                continue
            entries[path] = (mode, kind, object_sha)
        if len(entries) > 50000:
            fail("Git tree is too large to inspect safely")
        return entries

    def blob(self, object_sha: str) -> bytes:
        if not valid_sha(object_sha):
            fail("Git blob SHA is invalid")
        return self.git(["cat-file", "blob", object_sha])

    def contents(self, tree: dict[str, tuple[str, str, str]], path: str) -> bytes | None:
        entry = tree.get(path)
        return self.blob(entry[2]) if entry else None

    def parents(self, revision: str) -> list[str]:
        raw = self.git(["show", "-s", "--format=%P", revision]).decode("ascii").strip()
        return raw.split() if raw else []

    def first_parent_chain(self, revision: str) -> list[str]:
        commits = self.git(["rev-list", "--first-parent", revision]).decode("ascii").splitlines()
        if len(commits) > 20000:
            fail("trusted main history is too long to inspect safely")
        if any(not valid_sha(item) for item in commits):
            fail("Git returned an invalid commit history")
        return commits

    def ancestor(self, old: str, new: str) -> bool:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        result = subprocess.run(["git", "merge-base", "--is-ancestor", old, new], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, check=False)
        if result.returncode not in (0, 1):
            fail("cannot verify trusted Git ancestry")
        return result.returncode == 0

    def patch_digest(self, base: str, head: str, paths: list[str]) -> str:
        if paths != sorted(set(paths)) or not paths or any(not valid_repo_path(path) for path in paths):
            fail("routine patch path list is invalid")
        args = [
            "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--binary",
            "--full-index", "--no-color", "--src-prefix=a/", "--dst-prefix=b/",
            "--unified=3", base, head, "--", *paths,
        ]
        return sha256(self.git(args))


def load_trusted_manifests(git: GitObjects, base_sha: str) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, Any]]]:
    base_tree = git.tree(base_sha)
    required_raw = git.contents(base_tree, "policy/required-tests.json")
    routine_raw = git.contents(base_tree, "policy/routine-patches.json")
    if required_raw is None or routine_raw is None:
        fail("trusted policy manifests are missing from the current base")
    required = validate_required_manifest(parse_json(required_raw, "required-test manifest"))
    proof, patches = validate_routine_manifest(parse_json(routine_raw, "routine-patch manifest"))
    return required, proof, patches


def bootstrap_commit(git: GitObjects, base_sha: str, proof: dict[str, Any]) -> str:
    parent_sha = proof["first_parent"]
    matches: list[str] = []
    for commit in git.first_parent_chain(base_sha):
        parents = git.parents(commit)
        if parents and parents[0] == parent_sha:
            tree = git.tree(commit)
            good = True
            for path, expected_hash in proof["anchors"].items():
                content = git.contents(tree, path)
                if content is None or sha256(content) != expected_hash:
                    good = False
                    break
            if good:
                matches.append(commit)
    if len(matches) != 1:
        fail("trusted bootstrap proof is missing or ambiguous")
    return matches[0]


def required_removal(required: list[dict[str, str]], base_tree: dict[str, Any], head_tree: dict[str, Any], changed: list[dict[str, Any]]) -> list[str]:
    removed: set[str] = set()
    for item in required:
        path = item["path"]
        if path in base_tree and path not in head_tree:
            removed.add(path)
    for item in changed:
        if item.get("status") in {"removed", "renamed"}:
            if item.get("filename") in REQUIRED_IDS.values() or item.get("previous_filename") in REQUIRED_IDS.values():
                removed.add(item.get("previous_filename") or item.get("filename"))
    return sorted(removed)


def changed_paths_from_trees(base_tree: dict[str, Any], head_tree: dict[str, Any]) -> set[str]:
    return {
        path for path in set(base_tree) | set(head_tree)
        if base_tree.get(path) != head_tree.get(path)
    }


def api_changed_paths(files: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for item in files:
        filename = item.get("filename")
        if not valid_repo_path(filename):
            fail("GitHub returned an invalid changed path")
        result.add(filename)
        previous = item.get("previous_filename")
        if previous is not None:
            if not valid_repo_path(previous):
                fail("GitHub returned an invalid previous path")
            result.add(previous)
    return result


def parse_summary(body: Any) -> dict[str, str]:
    if not isinstance(body, str):
        fail("pull request summary is missing")
    found: dict[str, list[str]] = {}
    current: str | None = None
    labels = {name: name + ":" for name in SUMMARY_FIELDS}
    for line in body.splitlines():
        match = next((name for name, prefix in labels.items() if line.startswith(prefix)), None)
        if match is not None:
            if match in found:
                fail(f"pull request summary repeats {match}")
            current = match
            found[current] = [line[len(labels[current]):].strip()]
        elif current is not None:
            found[current].append(line.strip())
        elif line.strip():
            fail("pull request summary has text outside the template fields")
    if set(found) != set(SUMMARY_FIELDS):
        fail("pull request summary is missing required template fields")
    values = {key: "\n".join(part for part in parts if part).strip() for key, parts in found.items()}
    case = values["Simulation case"]
    if case not in CASES:
        fail("pull request summary has an unknown Simulation case")
    if any(not values[key] or "[details]" in values[key].lower() for key in SUMMARY_FIELDS if key != "Tests added" and key != "Tests removed"):
        fail("pull request summary contains an empty or template field")
    for key in ("Tests added", "Tests removed"):
        value = values[key]
        if value.lower() != "none" and ("[paths" in value.lower() or not URL_RE.search(value)):
            fail(f"pull request summary field {key} must say none or list paths and links")
    role = values["Reviewer role"]
    expected_role = "not required" if case == "routine" else "simulated by an independent agent"
    if role != expected_role:
        fail("pull request summary has an invalid Reviewer role")
    if case == "required-test removal":
        fail("required-test removal is blocked")
    return values


def urls_in(text: str) -> list[str]:
    return URL_RE.findall(text)


def verdict_comment_head(comment: dict[str, Any]) -> str | None:
    body = comment.get("body")
    if not isinstance(body, str) or "SIMULATED REVIEW VERDICT" not in body:
        return None
    fields = re.findall(r"(?m)^Head SHA: ([^\r\n]*)$", body)
    if len(fields) != 1:
        return None
    match = re.fullmatch(r"`([0-9a-f]{40})`", fields[0])
    return match.group(1) if match else None


def is_stale_verdict_comment(comment: dict[str, Any], expected_head: str) -> bool:
    body = comment.get("body")
    return (
        isinstance(body, str)
        and "SIMULATED REVIEW VERDICT" in body
        and (comment_head := verdict_comment_head(comment)) is not None
        and comment_head != expected_head
    )


def parse_verdict_comment(comment: dict[str, Any]) -> dict[str, Any] | None:
    body = comment.get("body")
    if not isinstance(body, str) or "SIMULATED REVIEW VERDICT" not in body:
        return None
    author = comment.get("user")
    if not isinstance(author, dict) or author.get("login") != BOT_LOGIN or author.get("type") != "Bot" or author.get("id") != BOT_USER_ID:
        fail("simulated verdict comment has the wrong source")
    comment_id = comment.get("id")
    if isinstance(comment_id, bool) or not isinstance(comment_id, int) or comment_id < 1:
        fail("simulated verdict comment has an invalid ID")
    if comment.get("updated_at") and comment.get("created_at") != comment.get("updated_at"):
        fail("simulated verdict comment was edited")
    pattern = re.compile(
        r"\A### SIMULATED REVIEW VERDICT\n\n"
        r"This is a simulated reviewer-agent decision\. It is not a human review or approval\.\n\n"
        r"Case ID: `([^`\n]+)`\n\n"
        r"Decision: `(approved|changes_requested)`\n\n"
        r"Head SHA: `([0-9a-f]{40})`\n\n"
        r"Reason:\n(.+?)\n\n"
        r"Evidence:\n((?:- https://[^\s]+\n?)+)"
        r"(?:\nSupersedes comment ID: `([1-9][0-9]*)`\n)?\Z",
        re.DOTALL,
    )
    match = pattern.fullmatch(body)
    if not match:
        fail("simulated verdict comment is malformed")
    case_id, decision, head_sha, reason, evidence_text, supersedes = match.groups()
    evidence = [line[2:] for line in evidence_text.splitlines() if line.startswith("- ")]
    if not case_id.strip() or len(case_id) > 80 or not reason.strip() or len(reason) > 4000 or not evidence or len(evidence) > 20:
        fail("simulated verdict comment has empty or oversized fields")
    if decision == "changes_requested" and supersedes is not None:
        fail("a negative verdict cannot supersede a comment")
    return {
        "id": comment_id,
        "case": case_id,
        "decision": decision,
        "head": head_sha,
        "reason": reason,
        "evidence": evidence,
        "supersedes": int(supersedes) if supersedes else None,
        "created_at": comment.get("created_at", ""),
    }


def current_verdict_comments(comments: list[dict[str, Any]], expected_head: str) -> tuple[list[dict[str, Any]], bool]:
    parsed: list[dict[str, Any]] = []
    stale_found = False
    for comment in comments:
        body = comment.get("body")
        if not isinstance(body, str) or "SIMULATED REVIEW VERDICT" not in body:
            continue
        if is_stale_verdict_comment(comment, expected_head):
            stale_found = True
            continue
        item = parse_verdict_comment(comment)
        if item is not None:
            if item["head"] != expected_head:
                fail("simulated verdict comment has an invalid head scope")
            parsed.append(item)
    return parsed, stale_found


def verdict_state(comments: list[dict[str, Any]], expected_case: str, head_sha: str) -> tuple[str, str, list[str]]:
    parsed, stale_found = current_verdict_comments(comments, head_sha)
    ids = [item["id"] for item in parsed]
    if len(ids) != len(set(ids)):
        fail("simulated verdict comments have duplicate IDs")
    current = [item for item in parsed if item["head"] == head_sha]
    if not current:
        if stale_found:
            return "failure", "Only stale simulated verdict comments exist", []
        return "pending", "A current simulated reviewer verdict is required", []
    if any(item["case"] != expected_case for item in current):
        fail("simulated verdict case does not match the pull request")
    current.sort(key=lambda item: (item["created_at"], item["id"]))
    if len(current) == 1:
        item = current[0]
        if item["supersedes"] is not None:
            fail("verdict supersedes a missing or non-current comment")
        if item["decision"] == "changes_requested":
            return "failure", "Current simulated review requests changes", item["evidence"]
        return "success", "Current simulated reviewer accepted this exact head", item["evidence"]
    if len(current) != 2:
        fail("simulated verdict history has conflicting or out-of-order comments")
    old, new = current
    if old["decision"] != "changes_requested" or old["supersedes"] is not None:
        fail("only one negative verdict can precede an accepted verdict")
    if new["decision"] != "approved" or new["supersedes"] != old["id"]:
        fail("accepted verdict must explicitly supersede the one negative verdict")
    if old["created_at"] and new["created_at"] and old["created_at"] >= new["created_at"]:
        fail("simulated verdict comments are out of order")
    return "success", "Accepted verdict explicitly supersedes the current negative verdict", new["evidence"]


def evaluate(
    *,
    pr: dict[str, Any],
    current_main_sha: str,
    live_head_sha: str,
    base_tree: dict[str, tuple[str, str, str]],
    head_tree: dict[str, tuple[str, str, str]],
    required: list[dict[str, str]],
    patches: list[dict[str, Any]],
    bootstrap_sha: str,
    changed: list[dict[str, Any]],
    patch_digest: str,
    ci: dict[str, Any],
    comments: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    blob_cache: dict[str, bytes] | None = None,
) -> tuple[str, str]:
    try:
        try:
            number = int(pr["number"])
            base = pr["base"]
            head = pr["head"]
            pr_base_sha = base["sha"]
            pr_head_sha = head["sha"]
            base_ref = base["ref"]
            head_repo = head["repo"]["full_name"]
            author = pr["user"]["login"]
        except (KeyError, TypeError, ValueError):
            fail("pull request record is incomplete")
        if pr.get("state") != "open" or base_ref != BASE_BRANCH or head_repo != REPOSITORY:
            fail("pull request is not an open same-repository PR to main")
        actor = pr.get("user")
        if author != BOT_LOGIN or not isinstance(actor, dict) or actor.get("type") != "Bot" or actor.get("id") != BOT_USER_ID:
            fail("pull request author is not github-actions[bot]")
        if pr_base_sha != current_main_sha:
            fail("pull request base is not the current live main revision")
        if pr_head_sha != live_head_sha:
            fail("pull request head branch moved")
        if not valid_sha(pr_base_sha) or not valid_sha(pr_head_sha):
            fail("pull request revision is not a full commit SHA")

        # This must run before PR metadata or verdict parsing. A missing summary
        # or accepted verdict cannot change the result for required-test removal.
        removed = required_removal(required, base_tree, head_tree, changed)
        if removed:
            return "failure", "Required test removed or renamed: " + ", ".join(removed)

        for item in required:
            path = item["path"]
            base_content = base_tree.get(path)
            head_content = head_tree.get(path)
            if base_content is None:
                fail("trusted base is missing a required test")
            base_bytes = _blob_from_entry(base_content, blob_cache)
            if sha256(base_bytes) != item["sha256"]:
                fail("trusted base required-test hash does not match its manifest")
            if head_content is None:
                fail("required test is missing from the pull request head")
            if sha256(_blob_from_entry(head_content, blob_cache)) != item["sha256"]:
                # A required-test edit is review work, never an allowlisted routine.
                pass

        actual_paths = changed_paths_from_trees(base_tree, head_tree)
        if actual_paths != api_changed_paths(changed):
            fail("GitHub changed-file list does not match the base/head Git trees")

        # Check structured summary only after the removal branch above.
        summary = parse_summary(pr.get("body"))
        case = summary["Simulation case"]
        expected_case = CASES[case]
        sensitive = bool(actual_paths & PROTECTED_PATHS)
        required_edit = any(
            base_tree[item["path"]][2] != head_tree[item["path"]][2]
            for item in required
        )
        routine = None
        if case == "routine" and not sensitive and not required_edit and pr_base_sha == bootstrap_sha:
            for item in patches:
                if actual_paths == set(item["paths"]) and patch_digest == item["sha256"]:
                    routine = item
                    break
        needs_review = routine is None
        if case == "routine" and routine is None:
            needs_review = True
        if case == "required-test removal":
            return "failure", "Required-test removal is blocked"

        # Every URL in the summary must be a verified same-repository PR,
        # ancestor commit/blob, or an exact-head CI run. External URLs fail.
        summary_urls = urls_in("\n".join(summary.values()))
        if not summary_urls:
            fail("pull request summary has no repository evidence URLs")
        checked_summary = [_checked_evidence(url, evidence, number, pr_head_sha) for url in summary_urls]
        for field in ("Tests added", "Tests removed"):
            value = summary[field]
            if value.lower() == "none":
                continue
            for url in urls_in(value):
                item = evidence[url]
                if _evidence_kind(url, evidence, number, pr_head_sha) != "history" or not is_test_file_path(item.get("path")):
                    fail(f"{field} must link to verified test files")
        relevant = summary["Relevant tests and runs"]
        relevant_urls = urls_in(relevant)
        kinds = {_evidence_kind(url, evidence, number, pr_head_sha) for url in relevant_urls}
        if not any(kind in {"pr", "history"} for kind in kinds) or "ci" not in kinds:
            fail("Relevant tests and runs must link to this PR or its history and exact-head CI")
        if any(not item for item in checked_summary):
            fail("pull request summary contains invalid evidence")

        if needs_review:
            verdict, reason, verdict_urls = verdict_state(comments, expected_case, pr_head_sha)
            if verdict == "pending":
                return "pending", reason
            if verdict != "success":
                return "failure", reason
            verdict_kinds = {_evidence_kind(url, evidence, number, pr_head_sha) for url in verdict_urls}
            if not any(kind in {"pr", "history"} for kind in verdict_kinds) or "ci" not in verdict_kinds:
                fail("simulated verdict evidence must link to PR history and exact-head CI")
            for url in verdict_urls:
                _checked_evidence(url, evidence, number, pr_head_sha)
        else:
            reason = "Exact trusted routine patch"

        ci_state, ci_reason = validate_ci(ci, evidence, number, pr_head_sha)
        if ci_state != "success":
            return ci_state, ci_reason
        if routine is not None:
            return "success", f"{reason}; all required checks pass"
        return "success", f"{reason}; exact-head demo-tests passed"
    except GateError as error:
        return "failure", str(error)


def _blob_from_entry(entry: tuple[str, ...], blob_cache: dict[str, bytes] | None = None) -> bytes:
    """The evaluator reads only trusted required-test blobs."""
    if len(entry) == 4:
        return entry[3]
    if blob_cache is not None and entry[2] in blob_cache:
        return blob_cache[entry[2]]
    fail("required-test blob bytes are unavailable to the evaluator")


def _evidence_kind(url: str, evidence: dict[str, dict[str, Any]], number: int, head: str) -> str:
    item = evidence.get(url)
    if not isinstance(item, dict) or not item.get("valid"):
        fail("evidence URL is missing, invalid, or from another repository")
    if item.get("kind") == "pr" and item.get("number") == number:
        return "pr"
    if item.get("kind") == "history" and item.get("ancestor") is True:
        return "history"
    if item.get("kind") == "ci" and item.get("head_sha") == head and item.get("success") is True:
        return "ci"
    fail("evidence URL is for the wrong PR, history, or CI SHA")


def _checked_evidence(url: str, evidence: dict[str, dict[str, Any]], number: int, head: str) -> bool:
    _evidence_kind(url, evidence, number, head)
    return True


def is_test_file_path(path: Any) -> bool:
    if not isinstance(path, str) or not valid_repo_path(path):
        return False
    return bool(re.search(
        r"(?:^|/)(?:test_[^/]+|[^/]+_test|[^/]+\.(?:test|spec))\.(?:py|js|mjs|ts|tsx)$",
        path,
    )) and path.startswith(("tests/", "api/tests/", "web/tests/"))


def validate_ci(ci: dict[str, Any], evidence: dict[str, dict[str, Any]], number: int, head: str) -> tuple[str, str]:
    if not isinstance(ci, dict) or ci.get("head_sha") != head or ci.get("workflow_path") != CI_WORKFLOW_PATH:
        return "failure", "No exact-head demo-tests Actions run exists"
    if ci.get("source_app_id") != ACTIONS_APP_ID:
        return "failure", "demo-tests check source is not the trusted GitHub Actions app"
    if ci.get("status") != "completed":
        return "pending", "Exact-head demo-tests run is not complete"
    if ci.get("conclusion") != "success" or ci.get("job_name") != CI_JOB_NAME or ci.get("job_conclusion") != "success":
        return "failure", "Exact-head demo-tests Actions run did not pass"
    url = ci.get("html_url")
    item = evidence.get(url) if isinstance(url, str) else None
    if not isinstance(item, dict) or item.get("kind") != "ci" or item.get("head_sha") != head or item.get("success") is not True:
        return "failure", "Exact-head demo-tests run evidence is invalid"
    return "success", "Exact-head demo-tests passed"


def parse_urls_checked(text: str, github: "GitHub", git: GitObjects, pr_number: int, head_sha: str, base_sha: str) -> dict[str, dict[str, Any]]:
    found = urls_in(text)
    result: dict[str, dict[str, Any]] = {}
    for url in found:
        result[url] = github.verify_evidence(url, git, pr_number, head_sha)
    return result


class GitHub:
    def __init__(self, token: str, repo: str = REPOSITORY):
        if repo != REPOSITORY:
            fail("repository is not allowlisted")
        self.token = token
        self.repo = repo
        self.api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        self.server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        self.known_snapshot: tuple[int, str, str] | None = None

    def request(self, method: str, path: str, payload: Any = None, accept: str = "application/vnd.github+json") -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.api.rstrip("/") + "/repos/" + self.repo + "/" + path.lstrip("/"),
            data=body,
            method=method,
            headers={
                "Accept": accept,
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-code-review-demo-policy",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            fail(f"GitHub API request failed (HTTP {error.code})")
        except urllib.error.URLError:
            fail("GitHub API request failed")
        if not raw:
            return None
        if accept.endswith(".diff") or accept.endswith(".patch"):
            return raw.decode("utf-8", "replace")
        return parse_json(raw, "GitHub response")

    def branch_sha(self, branch: str) -> str:
        encoded = urllib.parse.quote(branch, safe="")
        data = self.request("GET", f"branches/{encoded}")
        try:
            value = data["commit"]["sha"]
        except (TypeError, KeyError):
            fail("GitHub returned an invalid branch")
        if not valid_sha(value):
            fail("GitHub returned an invalid branch SHA")
        return value

    def pull(self, number: int) -> dict[str, Any]:
        data = self.request("GET", f"pulls/{number}")
        if not isinstance(data, dict):
            fail("GitHub returned an invalid pull request")
        return data

    def pull_files(self, number: int, expected: int) -> list[dict[str, Any]]:
        if expected < 0 or expected > 300:
            fail("pull request changed-file count is outside the safe limit")
        files: list[dict[str, Any]] = []
        for page in range(1, 5):
            data = self.request("GET", f"pulls/{number}/files?per_page=100&page={page}")
            if not isinstance(data, list):
                fail("GitHub returned an invalid changed-file list")
            files.extend(data)
            if len(data) < 100:
                break
        if len(files) != expected:
            fail("GitHub changed-file list is incomplete")
        return files

    def comments(self, number: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for page in range(1, 101):
            data = self.request("GET", f"issues/{number}/comments?per_page=100&page={page}")
            if not isinstance(data, list):
                fail("GitHub returned an invalid comment list")
            result.extend(data)
            if len(data) < 100:
                return result
        fail("pull request has too many comments to inspect safely")

    def workflow_run(self, run_id: str) -> dict[str, Any]:
        data = self.request("GET", f"actions/runs/{run_id}")
        if not isinstance(data, dict):
            fail("GitHub returned an invalid Actions run")
        return data

    def run_jobs(self, run_id: str) -> list[dict[str, Any]]:
        data = self.request("GET", f"actions/runs/{run_id}/jobs?per_page=100")
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            fail("GitHub returned invalid Actions jobs")
        return data["jobs"]

    def latest_ci(self, head_sha: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(CI_WORKFLOW_PATH, safe="")
        data = self.request("GET", f"actions/workflows/{encoded}/runs?head_sha={head_sha}&per_page=100")
        if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
            fail("GitHub returned invalid workflow runs")
        runs = [run for run in data["workflow_runs"] if run.get("head_sha") == head_sha and run.get("path") == CI_WORKFLOW_PATH]
        if not runs:
            return {"head_sha": head_sha, "workflow_path": CI_WORKFLOW_PATH, "status": "missing"}
        runs.sort(key=lambda run: (run.get("run_number", 0), run.get("created_at", "")))
        run = runs[-1]
        run_id = str(run.get("id", ""))
        if not run_id.isdigit():
            fail("GitHub returned an invalid workflow run ID")
        jobs = self.run_jobs(run_id)
        job_rows = [job for job in jobs if job.get("name") == CI_JOB_NAME]
        if len(job_rows) != 1:
            return {
                "head_sha": head_sha,
                "workflow_path": CI_WORKFLOW_PATH,
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "job_name": "missing-or-duplicate",
                "job_conclusion": "failure",
                "html_url": run.get("html_url"),
            }
        job = job_rows[0]
        check = self.demo_tests_check(head_sha, run_id, str(job.get("id", "")))
        return {
            "head_sha": run.get("head_sha"),
            "workflow_path": run.get("path"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "job_name": job.get("name"),
            "job_conclusion": job.get("conclusion"),
            "html_url": run.get("html_url"),
            "source_app_id": check["app_id"],
        }

    def demo_tests_check(self, head_sha: str, run_id: str, job_id: str) -> dict[str, Any]:
        data = self.request("GET", f"commits/{head_sha}/check-runs?filter=latest&per_page=100")
        if not isinstance(data, dict) or not isinstance(data.get("check_runs"), list):
            fail("GitHub returned invalid check runs")
        rows = [
            check for check in data["check_runs"]
            if check.get("name") == CI_JOB_NAME
            and check.get("head_sha") == head_sha
            and check.get("app", {}).get("id") == ACTIONS_APP_ID
        ]
        if len(rows) != 1:
            fail("demo-tests check is missing or has the wrong source")
        check = rows[0]
        details = urllib.parse.urlsplit(check.get("details_url", ""))
        match = re.fullmatch(r"/" + re.escape(REPOSITORY) + r"/actions/runs/(\d+)/job/(\d+)/?", details.path)
        if (
            details.netloc != "github.com"
            or not match
            or match.group(1) != run_id
            or match.group(2) != job_id
            or check.get("status") != "completed"
            or check.get("conclusion") != "success"
        ):
            fail("demo-tests is not a successful check from the trusted Actions source")
        return {"app_id": ACTIONS_APP_ID, "check": check}

    def verify_evidence(self, url: str, git: GitObjects, pr_number: int, head_sha: str) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.username or parsed.password:
            fail("evidence link must use the same public GitHub repository")
        prefix = "/" + REPOSITORY + "/"
        if not parsed.path.startswith(prefix):
            fail("evidence link points outside this repository")
        tail = parsed.path[len(prefix):]
        pr_match = re.fullmatch(r"pull/(\d+)(?:/(?:files|commits|checks))?/?", tail)
        if pr_match:
            number = int(pr_match.group(1))
            if number != pr_number:
                fail("evidence PR link points to another pull request")
            pr = self.pull(number)
            if pr.get("number") != number:
                fail("evidence PR link does not exist")
            if parsed.fragment:
                comment_match = re.fullmatch(r"issuecomment-(\d+)", parsed.fragment)
                if not comment_match or not any(str(item.get("id")) == comment_match.group(1) for item in self.comments(number)):
                    fail("evidence PR comment link does not exist")
            return {"valid": True, "kind": "pr", "number": number}
        commit_match = re.fullmatch(r"commit/([0-9a-f]{40})/?", tail)
        if commit_match:
            commit = commit_match.group(1)
            if not git.ancestor(commit, head_sha):
                fail("evidence commit is not in the current PR history")
            return {"valid": True, "kind": "history", "ancestor": True}
        blob_match = re.fullmatch(r"blob/([0-9a-f]{40})/(.+)", tail)
        if blob_match:
            commit, path = blob_match.groups()
            if not valid_repo_path(urllib.parse.unquote(path)) or not git.ancestor(commit, head_sha):
                fail("evidence file is not in the current PR history")
            tree = git.tree(commit)
            if urllib.parse.unquote(path) not in tree:
                fail("evidence file does not exist at the linked revision")
            return {"valid": True, "kind": "history", "ancestor": True, "path": urllib.parse.unquote(path)}
        run_match = re.fullmatch(r"actions/runs/(\d+)(?:/job/(\d+))?/?", tail)
        if run_match:
            run_id, job_id = run_match.groups()
            run = self.workflow_run(run_id)
            if run.get("head_sha") != head_sha or run.get("path") != CI_WORKFLOW_PATH:
                fail("Actions evidence is not for the exact PR head and trusted CI workflow")
            if run.get("status") != "completed" or run.get("conclusion") != "success":
                fail("Actions evidence run did not pass")
            jobs = self.run_jobs(run_id)
            jobs = [job for job in jobs if job.get("name") == CI_JOB_NAME and (job_id is None or str(job.get("id")) == job_id)]
            if len(jobs) != 1 or jobs[0].get("conclusion") != "success":
                fail("Actions evidence does not show a passing demo-tests job")
            self.demo_tests_check(head_sha, run_id, str(jobs[0].get("id", "")))
            return {"valid": True, "kind": "ci", "head_sha": head_sha, "success": True}
        fail("evidence URL is not an allowed PR, history, or Actions link")


def current_snapshot(github: GitHub, event: dict[str, Any], git: GitObjects) -> tuple[dict[str, Any], int, str, str, list[dict[str, Any]]]:
    if event.get("repository", {}).get("full_name") != REPOSITORY:
        fail("workflow event is from another repository")
    if event.get("action") in {"closed", "converted_to_draft"}:
        fail("pull request is not active")
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name in {"workflow_dispatch", "issue_comment"} and os.environ.get("GITHUB_REF") != "refs/heads/main":
        fail("trusted manual or comment workflow must run from main")
    if event_name == "workflow_dispatch":
        try:
            number = int(event["inputs"]["pr"])
            supplied_head = event["inputs"]["head"]
        except (KeyError, TypeError, ValueError):
            fail("workflow dispatch requires a PR number and exact head SHA")
        if not valid_sha(supplied_head):
            fail("workflow dispatch head is not a full SHA")
    elif event_name == "issue_comment":
        if not isinstance(event.get("issue"), dict) or not event["issue"].get("pull_request"):
            fail("issue-comment event is not attached to a pull request")
        try:
            number = int(event["issue"]["number"])
        except (KeyError, TypeError, ValueError):
            fail("issue-comment event has no PR number")
        supplied_head = None
    else:
        try:
            number = int(event["number"])
        except (KeyError, TypeError, ValueError):
            fail("pull request event has no PR number")
        supplied_head = None
    pr = github.pull(number)
    try:
        head_sha = pr["head"]["sha"]
        head_branch = pr["head"]["ref"]
        pr_base_sha = pr["base"]["sha"]
    except (KeyError, TypeError):
        fail("GitHub returned an incomplete pull request")
    if supplied_head is not None and supplied_head != head_sha:
        fail("workflow dispatch head is stale")
    live_base_sha = github.branch_sha(BASE_BRANCH)
    branch_sha = github.branch_sha(head_branch)
    github.known_snapshot = (number, live_base_sha, head_sha)
    if pr.get("base", {}).get("repo", {}).get("full_name") != REPOSITORY:
        fail("pull request base repository is not trusted")
    if pr.get("base", {}).get("ref") != BASE_BRANCH or pr_base_sha != live_base_sha:
        fail("pull request base is not the current live main revision")
    if pr.get("head", {}).get("repo", {}).get("full_name") != REPOSITORY:
        fail("pull request head must be in the trusted repository")
    if branch_sha != head_sha:
        fail("pull request head branch is not current")
    git.fetch(live_base_sha)
    git.fetch(head_sha)
    checkout_sha = git.git(["rev-parse", "HEAD"]).decode("ascii").strip()
    if checkout_sha != live_base_sha:
        fail("checked-out trusted policy revision is not the current live main")
    if not git.ancestor(live_base_sha, head_sha):
        fail("pull request head is not up to date with current main")
    files = github.pull_files(number, int(pr.get("changed_files", -1)))
    return pr, number, live_base_sha, head_sha, files


def latest_head_matches(github: GitHub, number: int, head_sha: str) -> bool:
    pr = github.pull(number)
    try:
        current_head = pr["head"]["sha"]
        branch = pr["head"]["ref"]
    except (KeyError, TypeError):
        return False
    return pr.get("state") == "open" and current_head == head_sha and github.branch_sha(branch) == head_sha


def latest_snapshot_matches(github: GitHub, number: int, base_sha: str, head_sha: str) -> bool:
    pr = github.pull(number)
    try:
        current_head = pr["head"]["sha"]
        branch = pr["head"]["ref"]
        current_base = pr["base"]["sha"]
    except (KeyError, TypeError):
        return False
    return (
        pr.get("state") == "open"
        and current_head == head_sha
        and current_base == base_sha
        and github.branch_sha(BASE_BRANCH) == base_sha
        and github.branch_sha(branch) == head_sha
    )


def policy_input_fingerprint(pr: dict[str, Any], comments: list[dict[str, Any]]) -> str:
    """Hash the PR summary and all comments that can affect a verdict."""
    verdict_comments = []
    for comment in comments:
        body = comment.get("body")
        if isinstance(body, str) and "SIMULATED REVIEW VERDICT" in body:
            verdict_comments.append({
                "id": comment.get("id"),
                "body": body,
                "updated_at": comment.get("updated_at"),
            })
    verdict_comments.sort(
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
    )
    snapshot = {
        "body": pr.get("body"),
        "verdict_comments": verdict_comments,
    }
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded)


def latest_policy_inputs_match(github: GitHub, number: int, fingerprint: str) -> bool:
    pr = github.pull(number)
    comments = github.comments(number)
    return policy_input_fingerprint(pr, comments) == fingerprint


def post_status(github: GitHub, head_sha: str, state: str, reason: str) -> None:
    if state not in {"success", "failure", "pending", "error"}:
        state = "error"
    run_url = f"{github.server}/{REPOSITORY}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    description = reason.replace("\n", " ")[:140] or "Policy check failed closed"
    github.request("POST", f"statuses/{head_sha}", {
        "state": state,
        "context": POLICY_CONTEXT,
        "description": description,
        "target_url": run_url,
    })


def publish_evaluation_status(
    github: GitHub,
    number: int,
    base_sha: str,
    head_sha: str,
    input_fingerprint: str,
    state: str,
    reason: str,
) -> tuple[str, str, bool]:
    """Publish only a current result and revoke success if its inputs moved."""
    if not latest_snapshot_matches(github, number, base_sha, head_sha):
        return "failure", "Pull request or trusted base changed during policy evaluation", False

    if state == "success" and not latest_policy_inputs_match(github, number, input_fingerprint):
        state = "failure"
        reason = "Pull request summary or verdict comments changed during policy evaluation"

    published_success = state == "success"
    post_status(github, head_sha, state, reason)

    if not latest_snapshot_matches(github, number, base_sha, head_sha):
        if published_success and exact_merged_snapshot_matches(
            github, number, base_sha, head_sha, input_fingerprint
        ):
            return state, reason, True
        reason = "Pull request or trusted base changed during policy publication"
        post_status(github, head_sha, "failure", reason)
        return "failure", reason, True
    if published_success and not latest_policy_inputs_match(github, number, input_fingerprint):
        reason = "Pull request summary or verdict comments changed during policy publication"
        post_status(github, head_sha, "failure", reason)
        return "failure", reason, True
    return state, reason, True


def exact_merged_snapshot_matches(
    github: GitHub,
    number: int,
    base_sha: str,
    head_sha: str,
    input_fingerprint: str,
) -> bool:
    """Accept only an exact two-parent merge with unchanged policy inputs."""
    try:
        def exact_merge_sha(candidate: Any) -> str | None:
            if not isinstance(candidate, dict):
                return None
            candidate_head = candidate.get("head")
            candidate_base = candidate.get("base")
            if (
                candidate.get("state") != "closed"
                or candidate.get("merged") is not True
                or not isinstance(candidate.get("merged_at"), str)
                or not candidate["merged_at"]
                or not isinstance(candidate_head, dict)
                or candidate_head.get("sha") != head_sha
                or not isinstance(candidate_base, dict)
                or candidate_base.get("sha") != base_sha
            ):
                return None
            candidate_merge_sha = candidate.get("merge_commit_sha")
            return candidate_merge_sha if valid_sha(candidate_merge_sha) else None

        pr = github.pull(number)
        merge_sha = exact_merge_sha(pr)
        if merge_sha is None:
            return False
        commit = github.request("GET", f"git/commits/{merge_sha}")
        parents = commit.get("parents") if isinstance(commit, dict) else None
        if not isinstance(parents, list) or len(parents) != 2:
            return False
        parent_shas = [parent.get("sha") if isinstance(parent, dict) else parent for parent in parents]
        if parent_shas != [base_sha, head_sha]:
            return False
        latest_pr = github.pull(number)
        if exact_merge_sha(latest_pr) != merge_sha:
            return False
        comments = github.comments(number)
        return policy_input_fingerprint(latest_pr, comments) == input_fingerprint
    except (GateError, KeyError, TypeError, AttributeError, OSError, subprocess.SubprocessError):
        return False


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    token = os.environ.get("GH_TOKEN")
    if not event_path or not token:
        print("policy gate requires the GitHub event and token", file=sys.stderr)
        return 2
    github: GitHub | None = None
    git = GitObjects()
    try:
        event = parse_json(open(event_path, "rb").read(), "workflow event")
        if not isinstance(event, dict):
            fail("workflow event is invalid")
        github = GitHub(token, os.environ.get("GITHUB_REPOSITORY", ""))
        pr, number, base_sha, head_sha, changed = current_snapshot(github, event, git)
        if latest_snapshot_matches(github, number, base_sha, head_sha):
            post_status(github, head_sha, "pending", "Trusted policy recheck is in progress")
        base_tree = git.tree(base_sha)
        head_tree = git.tree(head_sha)
        required, proof, patches = load_trusted_manifests(git, base_sha)
        removal = required_removal(required, base_tree, head_tree, changed)
        comments: list[dict[str, Any]] = []
        if removal:
            state, reason = "failure", "Required test removed or renamed: " + ", ".join(removal)
        else:
            bootstrap_sha = bootstrap_commit(git, base_sha, proof)
            ci = github.latest_ci(head_sha)
            comments = github.comments(number)
            evidence: dict[str, dict[str, Any]] = {}
            summary = parse_summary(pr.get("body"))
            for url in urls_in("\n".join(summary.values())):
                evidence[url] = github.verify_evidence(url, git, number, head_sha)
            current_comments, _ = current_verdict_comments(comments, head_sha)
            for parsed_comment in current_comments:
                for url in parsed_comment["evidence"]:
                    evidence[url] = github.verify_evidence(url, git, number, head_sha)
            ci_url = ci.get("html_url")
            if isinstance(ci_url, str) and ci_url not in evidence:
                try:
                    evidence[ci_url] = github.verify_evidence(ci_url, git, number, head_sha)
                except GateError:
                    pass
            patch_paths = sorted(changed_paths_from_trees(base_tree, head_tree))
            digest = git.patch_digest(base_sha, head_sha, patch_paths) if patch_paths else sha256(b"")
            blob_cache: dict[str, bytes] = {}
            for item in required:
                for tree in (base_tree, head_tree):
                    entry = tree.get(item["path"])
                    if entry:
                        blob_cache[entry[2]] = git.blob(entry[2])
            state, reason = evaluate(
                pr=pr,
                current_main_sha=base_sha,
                live_head_sha=head_sha,
                base_tree=base_tree,
                head_tree=head_tree,
                required=required,
                patches=patches,
                bootstrap_sha=bootstrap_sha,
                changed=changed,
                patch_digest=digest,
                ci=ci,
                comments=comments,
                evidence=evidence,
                blob_cache=blob_cache,
            )
        input_fingerprint = policy_input_fingerprint(pr, comments)
        state, reason, published = publish_evaluation_status(
            github,
            number,
            base_sha,
            head_sha,
            input_fingerprint,
            state,
            reason,
        )
        if not published:
            fail(reason)
        print(f"{state}: {reason}")
        return 0 if state == "success" else 1
    except (GateError, OSError, subprocess.SubprocessError) as error:
        snapshot = github.known_snapshot if github else None
        if snapshot:
            number, base_sha, head_sha = snapshot
            try:
                if latest_head_matches(github, number, head_sha):
                    post_status(github, head_sha, "failure", str(error))
            except (GateError, OSError, subprocess.SubprocessError):
                pass
        print(f"policy gate failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
