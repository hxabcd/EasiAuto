import base64
import hashlib
import json
import os
from pathlib import Path

import requests

# ── GitHub repositories & paths ────────────────────────────────────────
MANIFEST_REPO = "hxabcd/EasiAutoWeb"
MANIFEST_FILE_PATH = "public/update.json"
ANNOUNCEMENT_REPO = "hxabcd/EasiAutoWeb"
ANNOUNCEMENT_FILE_PATH = "public/announcements.json"
OWNER_REPO = os.getenv("GITHUB_REPOSITORY", "hxabcd/EasiAuto")
REQUEST_TIMEOUT = 300
VALID_SEVERITIES = ("info", "warning", "error")

# ── Shared token (in-memory, not persisted) ────────────────────────────
_token: str = ""


def set_token(value: str) -> None:
    global _token
    _token = value
    os.environ["RELEASE_PAT"] = value


def resolve_token() -> str:
    return _token or os.getenv("RELEASE_PAT", "")


def github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def get_default_branch(repo: str, token: str) -> str:
    resp = requests.get(
        f"https://api.github.com/repos/{repo}",
        headers=github_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("default_branch", "main")


def get_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with file_path.open("rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def fetch_json_from_repo(repo: str, file_path: str, token: str) -> tuple[dict | list, str]:
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    resp = requests.get(api_url, headers=github_headers(token), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    file_data = resp.json()
    content = base64.b64decode(file_data["content"]).decode("utf-8")
    return json.loads(content), file_data["sha"]


def put_json_to_repo(
    repo: str,
    file_path: str,
    sha: str | None,
    data: dict | list,
    message: str,
    token: str,
) -> None:
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    body = {
        "message": message,
        "content": base64.b64encode(json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8")).decode("utf-8"),
        "branch": get_default_branch(repo, token),
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(api_url, headers=github_headers(token), json=body, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
