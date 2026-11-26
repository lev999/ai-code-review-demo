"""Focused, offline fixtures for the trusted policy decision rules."""

import hashlib
import unittest
from unittest.mock import patch

from policy import gate


REPO = "https://github.com/lev999/ai-code-review-demo"
PR_URL = REPO + "/pull/42"
RUN_URL = REPO + "/actions/runs/99"
BOT = {"login": gate.BOT_LOGIN, "type": "Bot", "id": gate.BOT_USER_ID}
BASE = "a" * 40
HEAD = "b" * 40


def digest(data):
    return hashlib.sha256(data).hexdigest()


def entry(data, label):
    return ("100644", "blob", hashlib.sha1(label.encode()).hexdigest(), data)


def summary(case="judgment", body_links=True, tests_added="none", tests_removed="none"):
    links = f"[PR]({PR_URL}) [CI]({RUN_URL})" if body_links else "none"
    role = "not required" if case == "routine" else "simulated by an independent agent"
    return "\n".join((
        f"Simulation case: {case}",
        "Rules added, changed, and removed (give IDs or write none): RULE-1",
        "Old behavior: Move one task.",
        "New behavior: Move the selected tasks.",
        f"Tests added: {tests_added}",
        f"Tests removed: {tests_removed}",
        f"Relevant tests and runs: {links}",
        f"Reviewer role: {role}",
    ))


def comment(comment_id, decision, head=HEAD, supersedes=None, *, user=None, case="H9", reason="Checked the diff and evidence.", evidence=None, created="2026-11-26T10:00:00Z", malformed=False):
    links = evidence or [PR_URL, RUN_URL]
    body = (
        "### SIMULATED REVIEW VERDICT\n\n"
        "This is a simulated reviewer-agent decision. It is not a human review or approval.\n\n"
        f"Case ID: `{case}`\n\n"
        f"Decision: `{decision}`\n\n"
        f"Head SHA: `{head}`\n\n"
        f"Reason:\n{reason}\n\n"
        "Evidence:\n" + "".join(f"- {url}\n" for url in links)
    )
    if supersedes is not None:
        body += f"\nSupersedes comment ID: `{supersedes}`\n"
    if malformed:
        body = body.replace("Decision:", "Verdict:")
    return {
        "id": comment_id,
        "user": user or BOT,
        "created_at": created,
        "updated_at": created,
        "body": body,
    }


class PolicyGateTests(unittest.TestCase):
    def setUp(self):
        self.contents = {
            path: f"trusted {test_id}\n".encode()
            for test_id, path in gate.REQUIRED_IDS.items()
        }
        self.required = [
            {"id": test_id, "path": path, "sha256": digest(self.contents[path])}
            for test_id, path in gate.REQUIRED_IDS.items()
        ]
        self.base_tree = {path: entry(content, path) for path, content in self.contents.items()}
        self.base_tree["api/app.py"] = entry(b"def get_task(): return row['title'].strip()\n", "api-old")
        self.head_tree = dict(self.base_tree)
        self.changed = []
        self.pr = self.pull("judgment")
        self.patches = []
        self.patch_digest = "0" * 64
        self.ci = self.green_ci()
        self.evidence = {
            PR_URL: {"valid": True, "kind": "pr", "number": 42},
            RUN_URL: {"valid": True, "kind": "ci", "head_sha": HEAD, "success": True},
        }

    def pull(self, case="judgment", body=True):
        return {
            "number": 42,
            "state": "open",
            "base": {"ref": "main", "sha": BASE, "repo": {"full_name": gate.REPOSITORY}},
            "head": {"sha": HEAD, "repo": {"full_name": gate.REPOSITORY}},
            "user": BOT,
            "body": summary(case) if body else None,
        }

    def green_ci(self):
        return {
            "head_sha": HEAD,
            "workflow_path": gate.CI_WORKFLOW_PATH,
            "status": "completed",
            "conclusion": "success",
            "job_name": gate.CI_JOB_NAME,
            "job_conclusion": "success",
            "source_app_id": gate.ACTIONS_APP_ID,
            "html_url": RUN_URL,
        }

    def evaluate(self, comments=(), **updates):
        values = {
            "pr": self.pr,
            "current_main_sha": BASE,
            "live_head_sha": HEAD,
            "base_tree": self.base_tree,
            "head_tree": self.head_tree,
            "required": self.required,
            "patches": self.patches,
            "bootstrap_sha": BASE,
            "changed": self.changed,
            "patch_digest": self.patch_digest,
            "ci": self.ci,
            "comments": list(comments),
            "evidence": self.evidence,
        }
        values.update(updates)
        return gate.evaluate(**values)

    def make_routine(self):
        self.pr = self.pull("routine")
        changes = {
            "api/app.py": entry(b"def get_task(): return normalize_title(row['title'])\n", "api-new"),
            "api/task_text.py": entry(b"def normalize_title(value): return value.strip()\n", "helper"),
            "api/tests/test_task_text.py": entry(b"assert normalize_title(' x ') == 'x'\n", "unit-test"),
        }
        self.head_tree.update(changes)
        self.changed = [
            {"filename": "api/app.py", "status": "modified"},
            {"filename": "api/task_text.py", "status": "added"},
            {"filename": "api/tests/test_task_text.py", "status": "added"},
        ]
        paths = sorted(changes)
        self.patch_digest = "c" * 64
        self.patches = [{"id": "routine-title-normalization", "paths": paths, "sha256": self.patch_digest}]

    def test_manifest_requires_stable_unique_ids(self):
        parsed = gate.validate_required_manifest({"schema": 1, "tests": self.required})
        self.assertEqual({item["id"] for item in parsed}, set(gate.REQUIRED_IDS))
        broken = [dict(item) for item in self.required]
        broken[0]["id"] = broken[1]["id"]
        with self.assertRaises(gate.GateError):
            gate.validate_required_manifest({"schema": 1, "tests": broken})

    def test_exact_routine_patch_passes_only_after_exact_head_ci(self):
        self.make_routine()
        state, reason = self.evaluate()
        self.assertEqual(state, "success")
        self.assertIn("Exact trusted routine patch", reason)
        self.ci["status"] = "in_progress"
        state, _ = self.evaluate()
        self.assertEqual(state, "pending")
        self.ci["status"] = "completed"
        self.ci["source_app_id"] = 1
        state, _ = self.evaluate()
        self.assertEqual(state, "failure")

    def test_changed_routine_digest_or_base_requires_review(self):
        self.make_routine()
        self.patch_digest = "d" * 64
        state, _ = self.evaluate()
        self.assertEqual(state, "pending")
        self.patch_digest = self.patches[0]["sha256"]
        state, _ = self.evaluate(bootstrap_sha="e" * 40)
        self.assertEqual(state, "pending")

    def test_judgment_needs_current_accepted_verdict_and_explicit_supersession(self):
        self.head_tree["api/app.py"] = entry(b"def get_task(): return selected_titles()\n", "behavior")
        self.changed = [{"filename": "api/app.py", "status": "modified"}]
        negative = comment(501, "changes_requested")
        state, reason = self.evaluate([negative])
        self.assertEqual(state, "failure")
        self.assertIn("requests changes", reason)
        positive = comment(502, "approved", supersedes=501, created="2026-11-26T10:01:00Z")
        state, reason = self.evaluate([negative, positive])
        self.assertEqual(state, "success")
        self.assertIn("supersedes", reason)

    def test_stale_history_does_not_override_a_fresh_current_verdict(self):
        self.head_tree["api/app.py"] = entry(b"changed behavior\n", "behavior")
        self.changed = [{"filename": "api/app.py", "status": "modified"}]
        stale = comment(516, "changes_requested", head="c" * 40)
        current_negative = comment(517, "changes_requested", created="2026-11-26T10:01:00Z")
        current_positive = comment(518, "approved", supersedes=517, created="2026-11-26T10:02:00Z")
        state, _ = self.evaluate([stale, current_negative, current_positive])
        self.assertEqual(state, "success")

    def test_same_pull_cannot_authorize_its_gate_or_manifest_change(self):
        self.pr = self.pull("routine")
        path = "policy/routine-patches.json"
        self.base_tree[path] = entry(b'{"patches":[]}\n', "manifest-old")
        self.head_tree[path] = entry(b'{"patches":["self"]}\n', "manifest-new")
        self.changed = [{"filename": path, "status": "modified"}]
        self.patch_digest = "e" * 64
        self.patches = [{"id": "self-authorized", "paths": [path], "sha256": self.patch_digest}]
        state, reason = self.evaluate()
        self.assertEqual(state, "pending")
        self.assertIn("verdict", reason)

    def test_dispatch_decision_is_not_authority(self):
        self.head_tree["api/app.py"] = entry(b"changed behavior\n", "behavior")
        self.changed = [{"filename": "api/app.py", "status": "modified"}]
        # The workflow_dispatch `decision=accept` input is not an evaluate input.
        state, reason = self.evaluate([])
        self.assertEqual(state, "pending")
        self.assertIn("verdict", reason)

    def test_required_test_removal_blocks_before_summary_and_verdict(self):
        path = gate.REQUIRED_IDS["browser-reload"]
        self.head_tree.pop(path)
        self.pr = self.pull("required-test removal", body=False)
        self.changed = [{"filename": path, "status": "removed"}]
        positive = comment(503, "approved", case="H10")
        state, reason = self.evaluate([positive])
        self.assertEqual(state, "failure")
        self.assertIn(path, reason)

    def test_required_test_rename_blocks(self):
        path = gate.REQUIRED_IDS["task-api"]
        self.head_tree.pop(path)
        self.head_tree["api/tests/renamed_api_test.py"] = entry(b"same test\n", "renamed")
        self.pr = self.pull("required-test removal", body=False)
        self.changed = [{"filename": "api/tests/renamed_api_test.py", "previous_filename": path, "status": "renamed"}]
        state, reason = self.evaluate()
        self.assertEqual(state, "failure")
        self.assertIn(path, reason)

    def test_required_test_edit_routes_to_review(self):
        path = gate.REQUIRED_IDS["board-selection"]
        self.head_tree[path] = entry(b"edited test\n", "edited-test")
        self.changed = [{"filename": path, "status": "modified"}]
        state, _ = self.evaluate()
        self.assertEqual(state, "pending")

    def test_bad_manifest_source_hash_fails_closed(self):
        self.required[0] = dict(self.required[0], sha256="f" * 64)
        state, reason = self.evaluate()
        self.assertEqual(state, "failure")
        self.assertIn("trusted base required-test hash", reason)

    def test_stale_malformed_wrong_source_and_conflicting_verdicts_fail(self):
        self.head_tree["api/app.py"] = entry(b"changed behavior\n", "behavior")
        self.changed = [{"filename": "api/app.py", "status": "modified"}]
        cases = [
            ([comment(510, "approved", head="c" * 40)], "stale"),
            ([comment(511, "approved", malformed=True)], "malformed"),
            ([comment(512, "approved", user={"login": "someone-else", "type": "User", "id": 9})], "wrong source"),
            ([comment(513, "approved"), comment(514, "changes_requested", created="2026-11-26T10:01:00Z")], "out-of-order"),
            ([comment(519, "approved"), comment(520, "approved", created="2026-11-26T10:01:00Z")], "conflicting positives"),
            ([comment(521, "changes_requested"), comment(522, "approved", created="2026-11-26T10:01:00Z")], "missing supersedes"),
        ]
        for comments, label in cases:
            with self.subTest(label=label):
                state, _ = self.evaluate(comments)
                self.assertEqual(state, "failure")

    def test_summary_evidence_wrong_repo_or_sha_fails(self):
        self.pr = self.pull("judgment")
        self.evidence[RUN_URL] = {"valid": True, "kind": "ci", "head_sha": "c" * 40, "success": True}
        self.head_tree["api/app.py"] = entry(b"changed behavior\n", "behavior")
        self.changed = [{"filename": "api/app.py", "status": "modified"}]
        state, _ = self.evaluate([comment(515, "approved")])
        self.assertEqual(state, "failure")

    def test_tests_added_and_removed_require_verified_test_file_links(self):
        self.head_tree["api/app.py"] = entry(b"changed behavior\n", "behavior")
        self.changed = [{"filename": "api/app.py", "status": "modified"}]
        test_url = f"{REPO}/blob/{BASE}/tests/test_added.py"
        self.pr["body"] = summary(tests_added=f"[new test]({test_url})")
        self.evidence[test_url] = {
            "valid": True,
            "kind": "history",
            "ancestor": True,
            "path": "tests/test_added.py",
        }
        state, _ = self.evaluate([comment(523, "approved")])
        self.assertEqual(state, "success")

        self.evidence[test_url]["path"] = "api/app.py"
        state, reason = self.evaluate([comment(524, "approved")])
        self.assertEqual(state, "failure")
        self.assertIn("verified test files", reason)

    def test_policy_input_fingerprint_tracks_summary_and_verdict_edits(self):
        pr = self.pull()
        verdict = comment(525, "approved")
        baseline = gate.policy_input_fingerprint(pr, [verdict])
        irrelevant = {"id": 10, "body": "A general discussion comment", "updated_at": "now"}
        self.assertEqual(gate.policy_input_fingerprint(pr, [verdict, irrelevant]), baseline)

        edited_pr = dict(pr, body=summary("routine"))
        self.assertNotEqual(gate.policy_input_fingerprint(edited_pr, [verdict]), baseline)
        edited_verdict = dict(verdict, body=verdict["body"] + "\n")
        self.assertNotEqual(gate.policy_input_fingerprint(pr, [edited_verdict]), baseline)
        edited_verdict = dict(verdict, updated_at="2026-11-26T10:01:00Z")
        self.assertNotEqual(gate.policy_input_fingerprint(pr, [edited_verdict]), baseline)

    def test_changed_input_downgrades_success_before_publication(self):
        with (
            patch.object(gate, "latest_snapshot_matches", side_effect=[True, True]),
            patch.object(gate, "latest_policy_inputs_match", return_value=False),
            patch.object(gate, "post_status") as publish,
        ):
            state, reason, published = gate.publish_evaluation_status(
                object(), 42, BASE, HEAD, "snapshot", "success", "accepted"
            )
        self.assertTrue(published)
        self.assertEqual(state, "failure")
        self.assertIn("changed during policy evaluation", reason)
        self.assertEqual(publish.call_args.args[2], "failure")

    def test_changed_input_after_success_publication_revokes_status(self):
        with (
            patch.object(gate, "latest_snapshot_matches", side_effect=[True, True]),
            patch.object(gate, "latest_policy_inputs_match", side_effect=[True, False]),
            patch.object(gate, "post_status") as publish,
        ):
            state, reason, published = gate.publish_evaluation_status(
                object(), 42, BASE, HEAD, "snapshot", "success", "accepted"
            )
        self.assertTrue(published)
        self.assertEqual(state, "failure")
        self.assertIn("changed during policy publication", reason)
        self.assertEqual([call.args[2] for call in publish.call_args_list], ["success", "failure"])

    def test_current_live_base_head_and_branch_identity_are_required(self):
        state, reason = self.evaluate(current_main_sha="f" * 40)
        self.assertEqual(state, "failure")
        self.assertIn("current live main", reason)
        state, reason = self.evaluate(live_head_sha="f" * 40)
        self.assertEqual(state, "failure")
        self.assertIn("head branch moved", reason)


if __name__ == "__main__":
    unittest.main()
