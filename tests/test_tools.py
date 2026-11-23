"""Real file, folder and command behavior tested independently of the model."""
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gamenext.infrastructure.tool_runtime import computer, file_path, validate_url
from gamenext.infrastructure.document_reader import read_document


class ToolTests(unittest.TestCase):
    def test_read_write_backup_and_repeated_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "sample.txt"
            computer({"action": "write", "path": str(path), "content": "antes"})
            computer({"action": "write", "path": str(path), "content": "depois"})
            self.assertEqual(read_document(path), "depois")
            self.assertEqual(path.with_name("sample.txt.gamenext-backup").read_text(), "antes")
            # Second overwrite updates the single backup cleanly without artificial blocking.
            computer({"action": "write", "path": str(path), "content": "final"})
            self.assertEqual(read_document(path), "final")
            self.assertEqual(path.with_name("sample.txt.gamenext-backup").read_text(), "depois")

    def test_mkdir_list_and_run_command(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "sub"
            res = computer({"action": "mkdir", "path": str(folder)})
            self.assertTrue(folder.is_dir())
            self.assertEqual(res["created_folder"], str(folder.resolve()))
            drives = computer({"action": "list"})
            self.assertIn("drives", drives)
            cmd = computer({"action": "run_command", "command": "Write-Output 'ok-gn Êxito não encontrado'"})
            self.assertEqual(cmd["returncode"], 0)
            self.assertIn("ok-gn", cmd["stdout"])
            self.assertIn("Êxito", cmd["stdout"])

    def test_credential_store_and_non_http_urls_rejected(self):
        with self.assertRaises(PermissionError):
            file_path(str(Path.home() / ".ssh" / "id_rsa"))
        with self.assertRaises(ValueError):
            validate_url("file:///C:/Users")
        with self.assertRaises(ValueError):
            validate_url("https://user:secret@example.com")
