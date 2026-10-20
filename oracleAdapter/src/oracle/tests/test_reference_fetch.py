import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oracle.adapters.rxr.reference_sources import fetch
from oracle.adapters.rxr.original_identity import text_fingerprint


class Response(io.BytesIO):
    def __init__(self, body, length=None, etag=None):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length),
                        "ETag": '"' + (etag or hashlib.md5(body).hexdigest()) + '"'}


class ReferenceFetch(unittest.TestCase):
    def setUp(self):
        case = Path(__file__).resolve().parents[4]
        owned = case / "outputs/oracleAdapter/unit-temp"
        owned.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=owned)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.config = {"cache_relative_path": "outputs/oracleAdapter/reference-cache/fixture",
                       "maximum_file_bytes": 10000, "maximum_total_bytes": 10000,
                       "socket_timeout_seconds": 1, "wall_seconds": 5,
                       "files": [{"split": "fixture", "url": "https://storage.googleapis.com/rxr-data/fixture.jsonl.gz"}]}

    def test_cached_verified_source_does_not_download_again(self):
        body = gzip.compress(b'{"fixture":true}\n')
        with patch("urllib.request.urlopen", return_value=Response(body)) as request:
            first = fetch(self.root, self.config, self.root / "outputs/oracleAdapter/first")
            self.assertEqual(request.call_count, 1)
        with patch("urllib.request.urlopen", side_effect=AssertionError("duplicate download")):
            second = fetch(self.root, self.config, self.root / "outputs/oracleAdapter/second")
        self.assertFalse(first["files"][0]["reused"])
        self.assertTrue(second["files"][0]["reused"])

    def test_incomplete_transfer_never_becomes_accepted_asset(self):
        body = gzip.compress(b"fixture")
        with patch("urllib.request.urlopen", return_value=Response(body, length=len(body) + 1)):
            with self.assertRaisesRegex(RuntimeError, "Incomplete"):
                fetch(self.root, self.config, self.root / "outputs/oracleAdapter/failed")
        cache = self.root / self.config["cache_relative_path"]
        self.assertFalse((cache / "fixture.jsonl.gz").exists())
        self.assertEqual(len(list(cache.glob("*.partial-*"))), 1)

    def test_text_audit_does_not_erase_semantic_changes(self):
        self.assertEqual(text_fingerprint('  "go  left" ', True), text_fingerprint("go left", True))
        self.assertNotEqual(text_fingerprint("don't go left", True), text_fingerprint("go left", True))
        self.assertNotEqual(text_fingerprint("go left", True), text_fingerprint("go right", True))


if __name__ == "__main__":
    unittest.main()
