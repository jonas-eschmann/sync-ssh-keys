import base64
import contextlib
import io
import json
import pathlib
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from sync_ssh_keys import fetch_keys, main, update_authorized_keys


def public_key(seed):
    key_type = b"ssh-ed25519"
    data = len(key_type).to_bytes(4, "big") + key_type + (32).to_bytes(4, "big") + bytes([seed]) * 32
    return "ssh-ed25519 " + base64.b64encode(data).decode()


CURRENT = public_key(1)
OLD = public_key(2)
NEW = public_key(3)


class SyncKeysTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = pathlib.Path(self.directory.name) / "authorized_keys"

    def run_cli(self, keys, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["sync-ssh-keys", "example", "--path", str(self.path), *args]
        with patch("sys.argv", argv), patch("sync_ssh_keys.fetch_keys", return_value=keys):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main()
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_adds_missing_and_reports_named_and_unnamed_keys(self):
        original = f"# Local keys\n{CURRENT} laptop\n{OLD} Alice's old laptop\n{NEW}\n"
        self.path.write_text(original)

        result, stdout, stderr = self.run_cli([CURRENT, public_key(4)])

        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(self.path.read_text(), original + public_key(4) + "\n")
        self.assertIn("Added 1 new key", stdout)
        self.assertIn("Note: 2 local keys not on GitHub for 'example'.", stdout)
        self.assertIn("Alice's old laptop", stdout)
        self.assertIn("(unnamed key)", stdout)
        self.assertIn("--rm", stdout)

    def test_rm_preserves_matching_options_comments_and_unrecognized_lines(self):
        options = 'command="echo \\"hello world\\"",no-port-forwarding'
        kept = f"# Local keys\r\n\r\n{options} {CURRENT} laptop\r\nunrecognized line\r\n"
        self.path.write_bytes((kept + f"{OLD} old laptop\r\n").encode())
        self.path.chmod(0o600)

        result, stdout, stderr = self.run_cli([CURRENT, NEW], "--rm")

        self.assertEqual((result, stderr), (0, ""))
        self.assertEqual(self.path.read_bytes(), (kept + NEW + "\n").encode())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertIn("Removed 1 local key", stdout)
        self.assertIn("old laptop", stdout)
        self.assertNotIn("Run again", stdout)

    def test_empty_github_list_removes_keys_only_with_rm(self):
        original = f"# keep this\n\n{OLD} old laptop\n{CURRENT}\n"
        self.path.write_text(original)
        result, stdout, _ = self.run_cli([])
        self.assertEqual(result, 0)
        self.assertIn("Note: 2 local keys", stdout)
        self.assertEqual(self.path.read_text(), original)

        result, stdout, _ = self.run_cli([], "--rm")
        self.assertEqual(result, 0)
        self.assertIn("Removed 2 local keys", stdout)
        self.assertEqual(self.path.read_text(), "# keep this\n\n")

    def test_append_separates_unterminated_last_line_and_deduplicates_github_keys(self):
        self.path.write_text(CURRENT)
        added, extras = update_authorized_keys([CURRENT, NEW, NEW + " alias"], self.path)
        self.assertEqual((added, extras), (1, []))
        self.assertEqual(self.path.read_text(), CURRENT + "\n" + NEW + " alias\n")
        self.assertEqual(update_authorized_keys([CURRENT, NEW], self.path), (0, []))

    def test_fetch_failure_leaves_file_untouched(self):
        self.path.write_text(OLD)
        argv = ["sync-ssh-keys", "example", "--path", str(self.path), "--rm"]
        with patch("sys.argv", argv), patch("sync_ssh_keys.fetch_keys", side_effect=RuntimeError("offline")):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
        self.assertEqual(self.path.read_text(), OLD)


class FetchKeysTests(unittest.TestCase):
    def response(self, payload):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = json.dumps(payload).encode()
        return response

    def test_fetches_every_page(self):
        responses = [self.response([{"key": CURRENT}] * 100), self.response([{"key": NEW}])]
        with patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            self.assertEqual(fetch_keys("example"), [CURRENT] * 100 + [NEW])
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("per_page=100&page=2", urlopen.call_args.args[0])

    def test_failure_on_later_page_does_not_return_partial_keys(self):
        responses = [self.response([{"key": CURRENT}] * 100), urllib.error.URLError("offline")]
        with patch("urllib.request.urlopen", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "Network error"):
                fetch_keys("example")


if __name__ == "__main__":
    unittest.main()
