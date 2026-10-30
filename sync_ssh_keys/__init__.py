import argparse
import base64
import io
import json
import pathlib
import shlex
import sys
import urllib.error
import urllib.request


def fetch_keys(username):
    keys = []
    page = 1
    try:
        while True:
            url = f"https://api.github.com/users/{username}/keys?per_page=100&page={page}"
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError(f"GitHub API responded with status {response.status}")
                payload = json.loads(response.read().decode())
            if not isinstance(payload, list):
                raise RuntimeError("GitHub API returned an invalid key list")
            keys.extend(item["key"] for item in payload)
            if len(payload) < 100:
                return keys
            page += 1
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Unable to fetch keys for user {username}: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while contacting GitHub: {exc}") from exc


def parse_key(line):
    """Return a key's identity and comment, ignoring any authorized_keys options."""
    if not line.strip() or line.lstrip().startswith("#"):
        return None
    stream = io.StringIO(line)
    lexer = shlex.shlex(stream, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        key_type = next(lexer)
        if not key_type.startswith(("ssh-", "ecdsa-", "sk-")):
            key_type = next(lexer)
        if not key_type.startswith(("ssh-", "ecdsa-", "sk-")):
            return None
        key_data = base64.b64decode(next(lexer), validate=True)
    except (ValueError, StopIteration):
        return None
    # Read the comment verbatim: names may contain unmatched quotes or apostrophes.
    return (key_type, key_data), stream.read().strip()


def update_authorized_keys(keys, dest=None, remove=False):
    github_keys = {parse_key(key)[0]: key.strip() for key in keys}
    dest_path = pathlib.Path(dest or "~/.ssh/authorized_keys").expanduser()
    lines = []
    if dest_path.exists():
        with dest_path.open("r", encoding="utf-8", newline="") as fp:
            lines = fp.readlines()
    existing = set()
    extra_keys = []
    kept_lines = []
    for line in lines:
        parsed = parse_key(line)
        if parsed is not None:
            identity = parsed[0]
            existing.add(identity)
            if identity not in github_keys:
                extra_keys.append(parsed[1] or "(unnamed key)")
                if remove:
                    continue
        kept_lines.append(line)

    new_keys = [key for identity, key in github_keys.items() if identity not in existing]
    if new_keys or (remove and extra_keys):
        content = "".join(kept_lines)
        if new_keys and content and not content.endswith(("\n", "\r")):
            content += "\n"
        content += "".join(key + "\n" for key in new_keys)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with dest_path.open("w", encoding="utf-8", newline="") as fp:
            fp.write(content)
    return len(new_keys), extra_keys


def main():
    parser = argparse.ArgumentParser(description="Authorize GitHub user's SSH keys.")
    parser.add_argument("username", help="GitHub username")
    parser.add_argument("--path", type=str, default=None, help="Path to authorized_keys")
    parser.add_argument(
        "--rm", action="store_true",
        help="Remove local keys that are not on this GitHub user's account",
    )
    ns = parser.parse_args()
    try:
        keys = fetch_keys(ns.username)
        added, extra_keys = update_authorized_keys(keys, ns.path, remove=ns.rm)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    word = "key" if added == 1 else "keys"
    print(f"Added {added} new {word} for GitHub user '{ns.username}'.")
    count = len(extra_keys)
    word = "key" if count == 1 else "keys"
    if ns.rm:
        print(f"Removed {count} local {word} not on GitHub for '{ns.username}'.")
    else:
        print(f"Note: {count} local {word} not on GitHub for '{ns.username}'.")
    for name in extra_keys:
        print(f"  - {name}")
    if extra_keys and not ns.rm:
        print("Run again with --rm to remove these keys.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

