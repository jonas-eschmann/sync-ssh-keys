import argparse
import json
import os
import sys
import pathlib
import urllib.error
import urllib.request

def fetch_keys(username):
    url = f"https://api.github.com/users/{username}/keys"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"GitHub API responded with status {response.status}")
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Unable to fetch keys for user {username}: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while contacting GitHub: {exc}") from exc
    return [item.get("key") for item in payload if "key" in item]

def update_authorized_keys(keys, dest=None):
    dest_path = pathlib.Path(dest or "~/.ssh/authorized_keys").expanduser()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if dest_path.exists():
        with dest_path.open("r", encoding="utf-8") as fp:
            existing = {line.strip() for line in fp if line.strip()}
    new_keys = [k for k in keys if k not in existing]
    if new_keys:
        with dest_path.open("a", encoding="utf-8") as fp:
            for key in new_keys:
                fp.write(key + "\n")
    return len(new_keys)

def main():
    parser = argparse.ArgumentParser(description="Authorize GitHub user's SSH keys.")
    parser.add_argument("username", help="GitHub username")
    parser.add_argument("--path", type=str, default=None, help="Path to authorized_keys")
    ns = parser.parse_args()
    try:
        keys = fetch_keys(ns.username)
        added = update_authorized_keys(keys, ns.path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    word = "key" if added == 1 else "keys"
    print(f"Added {added} new {word} for GitHub user '{ns.username}'.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

