from __future__ import annotations

import json
import os
import sys
import pathlib
import urllib.error
import urllib.request
from typing import List

__all__ = [
    "fetch_keys",
    "update_authorized_keys",
    "main",
]

__version__ = "0.1.0"

def fetch_keys(username: str) -> List[str]:
    url = f"https://api.github.com/users/{username}/keys"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"GitHub API responded with status {response.status} for {username!r}."
                )
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Unable to fetch keys for user {username!r}: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while contacting GitHub: {exc}") from exc
    return [item["key"] for item in payload if "key" in item]


def update_authorized_keys(keys: List[str], dest: str | os.PathLike | None = None) -> int:
    dest_path = pathlib.Path(dest or "~/.ssh/authorized_keys").expanduser()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()
    if dest_path.exists():
        with dest_path.open("r", encoding="utf‑8") as fp:
            existing = {line.strip() for line in fp if line.strip()}

    new_keys = [k for k in keys if k not in existing]
    if not new_keys:
        return 0

    with dest_path.open("a", encoding="utf‑8") as fp:
        for key in new_keys:
            fp.write(key + "\n")
    return len(new_keys)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in {"‑h", "‑‑help"}:
        prog = os.path.basename(sys.argv[0])
        print(f"Usage: {prog} <github_username> [authorized_keys_path]", file=sys.stderr)
        return 1

    username: str = argv[0]
    dest: str | None = argv[1] if len(argv) > 1 else None

    try:
        keys = fetch_keys(username)
        added = update_authorized_keys(keys, dest)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    word = "key" if added == 1 else "keys"
    print(f"Added {added} new {word} for GitHub user '{username}'.")
    return 0

if __name__ == "__main__":
    main()
