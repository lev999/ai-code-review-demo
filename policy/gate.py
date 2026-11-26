"""Evaluate this controlled demo using the protected branch copy of this file."""
import json
import os
import urllib.request
from base64 import b64decode


def request(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(os.environ["GITHUB_API_URL"] + "/repos/" +
                                 os.environ["GITHUB_REPOSITORY"] + "/" + path,
                                 data=body, headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                                                     "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def blob(path, revision):
    return b64decode(request(f"contents/{path}?ref={revision}")["content"]).decode()


def decide(pr, paths, head, decision):
    required = {"tests/test_move.py", "tests/test_preserve.py"}
    missing = sorted(f["filename"] for f in paths if f["status"] == "removed" and f["filename"] in required)
    missing += [f["previous_filename"] for f in paths if f.get("previous_filename") in required]
    if missing:
        return "failure", "Required test removed: " + ", ".join(missing)
    if len(paths) == 1 and paths[0]["filename"] == "board.py" and paths[0]["status"] == "modified":
        old = blob("board.py", pr["base"]["sha"])
        new = blob("board.py", head)
        if old != new and new == old.replace("for key, state in tasks.items()", "for key, current_state in tasks.items()").replace("else state)", "else current_state)"):
            return "success", "Exact routine refactor; approved rules unchanged"
    if decision == "accept":
        return "success", "Simulated reviewer accepted this exact head"
    return "pending", "Business rule or unclassified change: simulated review required"


if __name__ == "__main__":
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)
    manual = os.environ["GITHUB_EVENT_NAME"] == "workflow_dispatch"
    number = int(event["inputs"]["pr"] if manual else event["number"])
    pr = request(f"pulls/{number}")
    head = pr["head"]["sha"]
    if manual and event["inputs"]["head"] != head:
        raise SystemExit("Stale simulated reviewer decision")
    files = request(f"pulls/{number}/files?per_page=100")
    if pr["changed_files"] != len(files):
        raise SystemExit("Incomplete change list")
    state, reason = decide(pr, files, head, event.get("inputs", {}).get("decision"))
    link = os.environ["GITHUB_SERVER_URL"] + "/" + os.environ["GITHUB_REPOSITORY"] + "/actions/runs/" + os.environ["GITHUB_RUN_ID"]
    request(f"statuses/{head}", {"state": state, "context": "demo-policy", "description": reason[:140], "target_url": link})
    print(state, reason)
