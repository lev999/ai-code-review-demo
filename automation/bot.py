#!/usr/bin/env python3
"""Run one public PR or simulated-verdict request from this trusted revision."""

import email.utils
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


REPOSITORY = "lev999/ai-code-review-demo"
SUPPORT_REF = "refs/heads/demo/pr-automation"
BOT_LOGIN = "github-actions[bot]"
API = "https://api.github.com"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class BotError(Exception):
    pass


class UncertainWrite(BotError):
    pass


class StaleState(BotError):
    pass


def fail(message):
    raise BotError(message)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("request JSON has a duplicate key")
        result[key] = value
    return result


def require_exact_keys(data, keys):
    if not isinstance(data, dict) or set(data) != set(keys):
        fail("request JSON has missing or unknown fields")


def require_text(value, name, maximum=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f"request field {name} is empty or too long")
    return value


def require_sha(value, name):
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        fail(f"request field {name} is not a full commit SHA")
    return value


def require_branch(value, name):
    if (not isinstance(value, str) or not BRANCH_RE.fullmatch(value)
            or value.startswith("/") or value.endswith("/")
            or ".." in value or "//" in value or value.startswith("-")):
        fail(f"request field {name} is not a valid branch name")
    return value


def load_request():
    path = Path(__file__).resolve().parent / "request.json"
    try:
        raw = path.read_bytes()
    except OSError:
        fail("automation/request.json is missing")
    if len(raw) > 65536:
        fail("automation/request.json is too large")
    try:
        return json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("automation/request.json is not valid JSON")


def check_run_context():
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        fail("repository allowlist check failed")
    if os.environ.get("GITHUB_REF") != SUPPORT_REF:
        fail("workflow did not run from the support branch")
    event_sha = os.environ.get("GITHUB_SHA", "")
    if not SHA_RE.fullmatch(event_sha):
        fail("workflow event has no full commit SHA")
    try:
        checkout_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        fail("cannot verify the checked-out revision")
    if checkout_sha != event_sha:
        fail("checked-out revision does not match the push event")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        fail("GitHub Actions token is missing")
    return token


def retry_delay(headers, attempt):
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(1, float(retry_after))
        except ValueError:
            try:
                when = email.utils.parsedate_to_datetime(retry_after).timestamp()
                return max(1, when - time.time())
            except (TypeError, ValueError, OverflowError):
                pass
    reset = headers.get("X-RateLimit-Reset")
    if reset:
        try:
            return max(1, float(reset) - time.time())
        except ValueError:
            pass
    return float(2 ** (attempt + 1))


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-code-review-demo-pr-automation",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 204:
                        return None
                    try:
                        return json.loads(response.read())
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        fail("GitHub returned invalid JSON")
            except urllib.error.HTTPError as error:
                transient = error.code == 429 or error.code in (500, 502, 503, 504)
                if method == "GET" and transient and attempt + 1 < attempts:
                    time.sleep(retry_delay(error.headers, attempt))
                    continue
                if method != "GET" and transient:
                    raise UncertainWrite(
                        f"write result is uncertain (HTTP {error.code}); remote state was checked"
                    ) from None
                if error.code in (401, 403):
                    fail(f"GitHub authorization conflict (HTTP {error.code})")
                fail(f"GitHub request failed (HTTP {error.code}, {method} {path})")
            except urllib.error.URLError:
                if method == "GET" and attempt + 1 < attempts:
                    time.sleep(float(2 ** (attempt + 1)))
                    continue
                if method != "GET":
                    raise UncertainWrite("write result is uncertain after a network error") from None
                fail("GitHub read failed after retries")
        fail("GitHub read failed after retries")


def api_path(suffix):
    return f"/repos/{REPOSITORY}/{suffix}"


def get_branch_sha(github, branch):
    encoded = urllib.parse.quote(branch, safe="")
    result = github.request("GET", api_path(f"branches/{encoded}"))
    try:
        return result["commit"]["sha"]
    except (TypeError, KeyError):
        fail("GitHub returned an invalid branch record")


def check_refs(github, request):
    current_head = get_branch_sha(github, request["head_branch"])
    current_base = get_branch_sha(github, request["base_branch"])
    if current_head != request["head_sha"]:
        raise StaleState("head branch is stale")
    if current_base != request["base_sha"]:
        raise StaleState("base branch is stale")


def list_pull_requests(github, head_branch):
    query = urllib.parse.urlencode({
        "state": "all",
        "head": f"{REPOSITORY.split('/')[0]}:{head_branch}",
        "per_page": "100",
    })
    found = []
    for page in range(1, 101):
        page_query = query + "&page=" + str(page)
        result = github.request("GET", api_path("pulls") + "?" + page_query)
        if not isinstance(result, list):
            fail("GitHub returned an invalid pull request list")
        found.extend(result)
        if len(result) < 100:
            return found
    fail("pull request list is too large to inspect safely")


def verify_pull_request(pr, request, require_bot=True):
    try:
        exact = (
            pr["head"]["repo"]["full_name"] == REPOSITORY
            and pr["head"]["ref"] == request["head_branch"]
            and pr["head"]["sha"] == request["head_sha"]
            and pr["base"]["ref"] == request["base_branch"]
            and pr["base"]["sha"] == request["base_sha"]
            and pr["state"] == "open"
        )
        actor = pr["user"]["login"]
    except (KeyError, TypeError):
        fail("GitHub returned an incomplete pull request")
    if not exact:
        raise StaleState("pull request head or base is stale or conflicting")
    if require_bot and actor != BOT_LOGIN:
        fail("pull request author is not the GitHub Actions bot")
    return actor


def report(action, permalink, actor, head_sha):
    print(json.dumps({
        "action": action,
        "permalink": permalink,
        "actor": actor,
        "head_sha": head_sha,
    }, sort_keys=True))


def open_pull_request(github, request):
    require_exact_keys(request, {
        "action", "head_branch", "head_sha", "base_branch", "base_sha", "title", "body"
    })
    request["head_branch"] = require_branch(request["head_branch"], "head_branch")
    request["base_branch"] = require_branch(request["base_branch"], "base_branch")
    request["head_sha"] = require_sha(request["head_sha"], "head_sha")
    request["base_sha"] = require_sha(request["base_sha"], "base_sha")
    request["title"] = require_text(request["title"], "title", 256)
    request["body"] = require_text(request["body"], "body")
    for marker in ("SIMULATED FEATURE REQUEST", "SIMULATED PRODUCT RULES"):
        if marker not in request["body"]:
            fail("pull request body must label simulated inputs")
    check_refs(github, request)

    matches = []
    for pr in list_pull_requests(github, request["head_branch"]):
        try:
            same_branch = (
                pr["head"]["repo"]["full_name"] == REPOSITORY
                and pr["head"]["ref"] == request["head_branch"]
            )
        except (KeyError, TypeError):
            fail("GitHub returned an incomplete pull request")
        if same_branch:
            matches.append(pr)
    if len(matches) > 1:
        fail("multiple pull requests conflict with this head branch")
    if matches:
        pr = matches[0]
        verify_pull_request(pr, request)
        if pr.get("title") != request["title"] or pr.get("body") != request["body"]:
            fail("existing pull request content conflicts with the request")
        check_refs(github, request)
        report("reused_pull_request", pr["html_url"], pr["user"]["login"], request["head_sha"])
        return

    payload = {
        "title": request["title"],
        "body": request["body"],
        "head": request["head_branch"],
        "base": request["base_branch"],
    }
    created = True
    try:
        pr = github.request("POST", api_path("pulls"), payload)
    except UncertainWrite:
        # Reconcile an uncertain write before any later attempt can create a duplicate.
        matches = [p for p in list_pull_requests(github, request["head_branch"])
                   if p.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY
                   and p.get("head", {}).get("ref") == request["head_branch"]]
        if len(matches) == 1:
            pr = matches[0]
            created = False
        elif not matches:
            raise BotError("PR write is uncertain; no matching PR exists, inspect state before retry")
        else:
            fail("PR write is uncertain and multiple matching PRs exist")
    try:
        verify_pull_request(pr, request)
    except StaleState:
        if created and pr.get("user", {}).get("login") == BOT_LOGIN:
            try:
                github.request("PATCH", api_path(f"pulls/{pr['number']}"), {"state": "closed"})
            except BotError:
                fail("new PR has a stale head or base; automatic close failed")
            fail("new PR had a stale head or base and was closed")
        raise
    if pr.get("title") != request["title"] or pr.get("body") != request["body"]:
        fail("created or reused pull request content conflicts with the request")
    try:
        check_refs(github, request)
    except StaleState:
        if created:
            try:
                github.request("PATCH", api_path(f"pulls/{pr['number']}"), {"state": "closed"})
            except BotError:
                fail("head or base changed after PR creation; automatic close failed")
        fail("head or base changed after PR creation; new PR was closed")
    report("opened_pull_request" if created else "reused_pull_request",
           pr["html_url"], pr["user"]["login"], request["head_sha"])


def list_comments(github, number):
    comments = []
    for page in range(1, 101):
        query = urllib.parse.urlencode({"per_page": "100", "page": str(page)})
        result = github.request("GET", api_path(f"issues/{number}/comments") + "?" + query)
        if not isinstance(result, list):
            fail("GitHub returned an invalid comment list")
        comments.extend(result)
        if len(result) < 100:
            return comments
    fail("comment list is too large to inspect safely")


def comment_decision(github, request):
    required = {
        "action", "pr_number", "case_id", "head_sha", "base_branch", "base_sha",
        "decision", "reason", "evidence_links",
    }
    if set(request) not in (required, required | {"supersedes"}):
        fail("request JSON has missing or unknown fields")
    number = request["pr_number"]
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        fail("request field pr_number is invalid")
    request["head_sha"] = require_sha(request["head_sha"], "head_sha")
    request["base_branch"] = require_branch(request["base_branch"], "base_branch")
    request["base_sha"] = require_sha(request["base_sha"], "base_sha")
    decision = request["decision"]
    if decision not in ("approved", "changes_requested"):
        fail("request field decision is unknown")
    case_id = require_text(request["case_id"], "case_id", 80)
    reason = require_text(request["reason"], "reason", 4000)
    links = request["evidence_links"]
    if (not isinstance(links, list) or not links or len(links) > 20
            or any(not isinstance(link, str) or any(ch.isspace() for ch in link)
                   or not link.startswith("https://github.com/lev999/ai-code-review-demo/")
                   or len(link) > 1000 for link in links)):
        fail("request field evidence_links must contain public repository links")
    has_supersedes = "supersedes" in request
    supersedes = request.get("supersedes")
    if has_supersedes:
        if isinstance(supersedes, bool) or not isinstance(supersedes, int) or supersedes < 1:
            fail("request field supersedes is invalid")
        if decision != "approved":
            fail("only an approved verdict can supersede a comment")
    pr = github.request("GET", api_path(f"pulls/{number}"))
    try:
        request["head_branch"] = pr["head"]["ref"]
    except (KeyError, TypeError):
        fail("GitHub returned an incomplete pull request")
    verify_pull_request(pr, request)
    if pr["user"]["login"] != BOT_LOGIN:
        fail("pull request author is not the GitHub Actions bot")
    if get_branch_sha(github, request["base_branch"]) != request["base_sha"]:
        fail("base branch is stale")

    body = (
        "### SIMULATED REVIEW VERDICT\n\n"
        "This is a simulated reviewer-agent decision. It is not a human review or approval.\n\n"
        f"Case ID: `{case_id}`\n\n"
        f"Decision: `{decision}`\n\n"
        f"Head SHA: `{request['head_sha']}`\n\n"
        f"Reason:\n{reason}\n\n"
        "Evidence:\n" + "\n".join(f"- {link}" for link in links) + "\n"
    )
    if has_supersedes:
        body += f"\nSupersedes comment ID: `{supersedes}`\n"
    comments = list_comments(github, number)
    exact = [c for c in comments if c.get("body") == body]
    bot_exact = [c for c in exact if c.get("user", {}).get("login") == BOT_LOGIN]
    if exact and not bot_exact:
        fail("matching comment exists under a non-bot account")
    if len(bot_exact) > 1:
        fail("duplicate simulated decision comments exist")
    if bot_exact:
        verify_pull_request(github.request("GET", api_path(f"pulls/{number}")), request)
        if get_branch_sha(github, request["head_branch"]) != request["head_sha"]:
            raise StaleState("head branch is stale")
        report("reused_simulated_decision_comment", bot_exact[0]["html_url"], BOT_LOGIN,
               request["head_sha"])
        return

    if get_branch_sha(github, request["head_branch"]) != request["head_sha"]:
        raise StaleState("head branch is stale")
    latest = github.request("GET", api_path(f"pulls/{number}"))
    verify_pull_request(latest, request)
    try:
        comment = github.request("POST", api_path(f"issues/{number}/comments"), {"body": body})
    except UncertainWrite:
        comments = list_comments(github, number)
        exact = [c for c in comments if c.get("body") == body]
        bot_exact = [c for c in exact if c.get("user", {}).get("login") == BOT_LOGIN]
        if len(bot_exact) == 1:
            comment = bot_exact[0]
        elif not exact:
            raise BotError("comment write is uncertain; no matching comment exists, inspect before retry")
        else:
            fail("comment write is uncertain and matching comments conflict")
    if comment.get("user", {}).get("login") != BOT_LOGIN:
        fail("simulated decision comment was not authored by the GitHub Actions bot")
    final_pr = github.request("GET", api_path(f"pulls/{number}"))
    try:
        still_current = (
            final_pr["head"]["sha"] == request["head_sha"]
            and final_pr["base"]["sha"] == request["base_sha"]
        )
    except (KeyError, TypeError):
        still_current = False
    if not still_current:
        fail("head or base changed during the comment write; the labeled stale comment is retained")
    report("posted_simulated_decision_comment", comment["html_url"],
           comment["user"]["login"], request["head_sha"])


def main():
    token = check_run_context()
    request = load_request()
    if not isinstance(request, dict):
        fail("request JSON must be an object")
    github = GitHub(token)
    action = request.get("action")
    if action == "open_pr":
        open_pull_request(github, request)
    elif action == "verdict_comment":
        comment_decision(github, request)
    else:
        fail("request action is unknown")


if __name__ == "__main__":
    try:
        main()
    except BotError as error:
        print(f"automation failed: {error}", file=sys.stderr)
        sys.exit(1)
