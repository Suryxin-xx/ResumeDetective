import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cli_ai
import paths
from scripts import check_repository_safety


class DataIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_legacy_data_is_copied_without_deleting_source(self):
        legacy = self.root / "project" / "data"
        target = self.root / "private"
        legacy.mkdir(parents=True)
        (legacy / "data.db").write_bytes(b"sqlite-placeholder")
        with patch.object(paths, "LEGACY_DATA_DIR", legacy), patch.object(paths, "DATA_DIR", target):
            migrated, _ = paths.migrate_legacy_data_if_needed()
        self.assertTrue(migrated)
        self.assertEqual((target / "data.db").read_bytes(), b"sqlite-placeholder")
        self.assertTrue((legacy / "data.db").is_file())

    def test_old_managed_paths_resolve_to_external_data(self):
        legacy = self.root / "project" / "data"
        target = self.root / "private"
        resume = target / "Resumes" / "resume.pdf"
        resume.parent.mkdir(parents=True)
        resume.write_bytes(b"pdf")
        with patch.object(paths, "LEGACY_DATA_DIR", legacy), patch.object(paths, "DATA_DIR", target):
            self.assertEqual(paths.resolve_data_path("data/Resumes/resume.pdf"), resume)
            self.assertEqual(paths.stored_data_path(resume), "data/Resumes/resume.pdf")
            self.assertEqual(paths.resolve_data_path(legacy / "Resumes" / "resume.pdf"), resume)

    def test_reasonix_env_is_written_only_to_private_data(self):
        reasonix_data = self.root / "private" / "reasonix"
        with patch.object(cli_ai, "REASONIX_DATA_DIR", reasonix_data):
            self.assertTrue(cli_ai.sync_local_reasonix_env("unit-test-placeholder"))
        self.assertIn("DEEPSEEK_API_KEY=unit-test-placeholder", (reasonix_data / ".env").read_text(encoding="utf-8"))

    def test_repository_scanner_blocks_runtime_data_and_plain_secret(self):
        candidate = self.root / "public.py"
        candidate.write_text('api_key = "safe runtime variable"\n', encoding="utf-8")
        secret = self.root / "bad.env"
        secret.write_text("DEEPSEEK_API_KEY=unit-test-placeholder\n", encoding="utf-8")
        with patch.object(check_repository_safety, "ROOT", self.root):
            findings = check_repository_safety.scan_paths(["data/data.db", "bad.env", "public.py"])
        finding_paths = {item[0] for item in findings}
        self.assertIn("data/data.db", finding_paths)
        self.assertIn("bad.env", finding_paths)
        self.assertNotIn("public.py", finding_paths)


if __name__ == "__main__":
    unittest.main()
