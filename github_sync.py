"""
github_sync.py
==============
Commits JSON files back to GitHub after writes.
Place at repo root alongside main.py.
"""

import os
import base64
import httpx

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "bpepoy/bgyfpy")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_API    = "https://api.github.com"


def commit_file(local_path, commit_message):
    if not GITHUB_TOKEN:
        return {"status": "error", "detail": "GITHUB_TOKEN not set"}

    headers = {
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    path     = local_path.lstrip("/")
    _root    = os.environ.get("DATA_ROOT",
               os.path.abspath(os.path.dirname(__file__)))
    abs_path = os.path.join(_root, path)

    print("[github_sync] root=" + _root)
    print("[github_sync] abs_path=" + abs_path)
    print("[github_sync] exists=" + str(os.path.exists(abs_path)))

    try:
        with open(abs_path, "rb") as f:
            content = f.read()
    except FileNotFoundError:
        return {"status": "error", "detail": "File not found: " + abs_path}

    content_b64 = base64.b64encode(content).decode()
    url  = GITHUB_API + "/repos/" + GITHUB_REPO + "/contents/" + path
    resp = httpx.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    sha  = resp.json().get("sha") if resp.status_code == 200 else None

    print("[github_sync] existing_sha=" + str(sha))

    payload = {
        "message": commit_message,
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = httpx.put(url, headers=headers, json=payload)
    print("[github_sync] put_status=" + str(resp.status_code))

    if resp.status_code in (200, 201):
        return {
            "status": "committed",
            "path":   path,
            "sha":    resp.json().get("content", {}).get("sha"),
            "url":    "https://github.com/" + GITHUB_REPO + "/blob/" + GITHUB_BRANCH + "/" + path,
        }
    else:
        return {
            "status": "error",
            "detail": resp.json().get("message", "Unknown GitHub API error"),
            "code":   resp.status_code,
        }


def commit_tree(files, commit_message):
    if not GITHUB_TOKEN:
        return {"status": "error", "detail": "GITHUB_TOKEN not set"}

    headers = {
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    base  = GITHUB_API + "/repos/" + GITHUB_REPO
    _root = os.environ.get("DATA_ROOT",
            os.path.abspath(os.path.dirname(__file__)))

    ref_resp = httpx.get(base + "/git/ref/heads/" + GITHUB_BRANCH, headers=headers)
    if ref_resp.status_code != 200:
        return {"status": "error", "detail": "Could not get branch ref"}
    base_sha = ref_resp.json()["object"]["sha"]

    commit_resp  = httpx.get(base + "/git/commits/" + base_sha, headers=headers)
    base_tree_sha= commit_resp.json()["tree"]["sha"]

    tree_items = []
    for path in files:
        path     = path.lstrip("/")
        abs_path = os.path.join(_root, path)
        if not os.path.exists(abs_path):
            continue
        with open(abs_path, "rb") as f:
            content = f.read()
        blob_resp = httpx.post(base + "/git/blobs", headers=headers,
                               json={"content": base64.b64encode(content).decode(),
                                     "encoding": "base64"})
        blob_sha = blob_resp.json().get("sha")
        if blob_sha:
            tree_items.append({
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha":  blob_sha,
            })

    if not tree_items:
        return {"status": "error", "detail": "No files found to commit"}

    tree_resp     = httpx.post(base + "/git/trees", headers=headers,
                               json={"base_tree": base_tree_sha, "tree": tree_items})
    new_tree_sha  = tree_resp.json().get("sha")

    new_commit    = httpx.post(base + "/git/commits", headers=headers,
                               json={"message": commit_message,
                                     "tree": new_tree_sha,
                                     "parents": [base_sha]})
    new_commit_sha= new_commit.json().get("sha")

    httpx.patch(base + "/git/refs/heads/" + GITHUB_BRANCH, headers=headers,
                json={"sha": new_commit_sha})

    return {
        "status": "committed",
        "files":  len(tree_items),
        "commit": new_commit_sha,
        "url":    "https://github.com/" + GITHUB_REPO + "/commit/" + new_commit_sha,
    }