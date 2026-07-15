"""
github_sync.py
==============
Utility for committing JSON files back to GitHub after writes.
Place in repo root alongside analytics_builder.py.

Usage:
    from github_sync import commit_file

    # After writing any JSON:
    commit_file(
        local_path="data/betting/parlays.json",
        commit_message="Update parlays.json - week 3 2026"
    )
"""

import os
import json
import base64
import httpx


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "bpepoy/bgyfpy")
GITHUB_BRANCH= os.environ.get("GITHUB_BRANCH", "main")
GITHUB_API   = "https://api.github.com"


def commit_file(local_path: str, commit_message: str) -> dict:
    """
    Read a local file and commit it to GitHub.

    Args:
        local_path: path relative to repo root
                    e.g. "data/betting/parlays.json"
        commit_message: git commit message

    Returns:
        {"status": "committed", "sha": "...", "path": "..."}
        or
        {"status": "error", "detail": "..."}
    """
    if not GITHUB_TOKEN:
        return {"status": "error", "detail": "GITHUB_TOKEN not set"}

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Normalize path (remove leading slash if present)
    path = local_path.lstrip("/")

    # Get absolute local path
    _root = os.environ.get("DATA_ROOT",
            os.path.abspath(os.path.join(os.path.dirname(__file__))))
    if path.startswith("data/"):
        abs_path = os.path.join(_root, path)
    else:
        abs_path = path

    # Read the file
    try:
        with open(abs_path, "rb") as f:
            content = f.read()
    except FileNotFoundError:
        return {"status": "error", "detail": f"File not found: {abs_path}"}

    content_b64 = base64.b64encode(content).decode()

    # Get current SHA (required for updates, not needed for new files)
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    resp = httpx.get(url, headers=headers,
                     params={"ref": GITHUB_BRANCH})
    sha = resp.json().get("sha") if resp.status_code == 200 else None

    # Commit
    payload = {
        "message": commit_message,
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha  # required for updates

    resp = httpx.put(url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        return {
            "status": "committed",
            "path":   path,
            "sha":    resp.json().get("content", {}).get("sha"),
            "url":    f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}/{path}",
        }
    else:
        return {
            "status": "error",
            "detail": resp.json().get("message", "Unknown GitHub API error"),
            "code":   resp.status_code,
        }


def commit_multiple(files: list[tuple], commit_message: str) -> list:
    """
    Commit multiple files. Each file committed separately.
    files: list of local_path strings
           e.g. ["data/fantasy/results.json", "data/betting/parlays.json"]

    For atomic multi-file commits use commit_tree() below.
    """
    return [commit_file(path, commit_message) for path in files]


def commit_tree(files: list[str], commit_message: str) -> dict:
    """
    Commit multiple files in a single atomic git commit.
    This is the correct approach for analytics builds that
    update many JSON files at once.

    files: list of local paths relative to repo root
    """
    if not GITHUB_TOKEN:
        return {"status": "error", "detail": "GITHUB_TOKEN not set"}

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    base = f"{GITHUB_API}/repos/{GITHUB_REPO}"
    _root = os.environ.get("DATA_ROOT",
            os.path.abspath(os.path.join(os.path.dirname(__file__))))

    # Step 1: Get current branch SHA
    ref_resp = httpx.get(f"{base}/git/ref/heads/{GITHUB_BRANCH}",
                         headers=headers)
    if ref_resp.status_code != 200:
        return {"status": "error", "detail": "Could not get branch ref"}
    base_sha = ref_resp.json()["object"]["sha"]

    # Step 2: Get base tree SHA
    commit_resp = httpx.get(f"{base}/git/commits/{base_sha}",
                            headers=headers)
    base_tree_sha = commit_resp.json()["tree"]["sha"]

    # Step 3: Create blobs for each file
    tree_items = []
    for path in files:
        path = path.lstrip("/")
        if path.startswith("data/"):
            abs_path = os.path.join(_root, path)
        else:
            abs_path = path

        try:
            with open(abs_path, "rb") as f:
                content = f.read()
        except FileNotFoundError:
            continue

        blob_resp = httpx.post(f"{base}/git/blobs", headers=headers,
                               json={"content": base64.b64encode(content).decode(),
                                     "encoding": "base64"})
        blob_sha = blob_resp.json().get("sha")
        if blob_sha:
            tree_items.append({
                "path":    path,
                "mode":    "100644",
                "type":    "blob",
                "sha":     blob_sha,
            })

    if not tree_items:
        return {"status": "error", "detail": "No files to commit"}

    # Step 4: Create new tree
    tree_resp = httpx.post(f"{base}/git/trees", headers=headers,
                           json={"base_tree": base_tree_sha,
                                 "tree": tree_items})
    new_tree_sha = tree_resp.json().get("sha")

    # Step 5: Create commit
    new_commit = httpx.post(f"{base}/git/commits", headers=headers,
                            json={"message":  commit_message,
                                  "tree":     new_tree_sha,
                                  "parents":  [base_sha]})
    new_commit_sha = new_commit.json().get("sha")

    # Step 6: Update branch ref
    httpx.patch(f"{base}/git/refs/heads/{GITHUB_BRANCH}",
                headers=headers,
                json={"sha": new_commit_sha})

    return {
        "status":  "committed",
        "files":   len(tree_items),
        "commit":  new_commit_sha,
        "url":     f"https://github.com/{GITHUB_REPO}/commit/{new_commit_sha}",
    }