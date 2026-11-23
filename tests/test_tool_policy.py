"""Tool autonomy, optional approval review, disabled tools and argument sanitization."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gamenext.application.tool_controller import ToolController, sanitize_arguments, parse_tool_arguments
from gamenext.infrastructure.storage import Repository
from gamenext.infrastructure.tool_specs import TOOLS


class PolicyTests(unittest.TestCase):
    def test_optional_review_denial_and_disabled_tool_does_not_start(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            repo = Repository(folder / "data.sqlite3")
            # Autonomous mode is default (False); explicit opt-in enforces review.
            self.assertFalse(repo.preference("tool_ask_changes", False))
            repo.set_preference("tool_ask_changes", True)
            controller = ToolController(repo, folder)
            results = []
            controller.result.connect(results.append)
            path = folder / "must-not-exist.txt"
            controller.execute({
                "id": "denied",
                "function": {
                    "name": "computer",
                    "arguments": json.dumps({"action": "write", "path": str(path), "content": "blocked"}),
                },
            })
            self.assertIsNotNone(controller.approval)
            controller.approve(False)
            self.assertFalse(path.exists())
            self.assertFalse(results[-1]["ok"])
            repo.set_preference("tool_enabled", {"computer": False})
            controller.execute({
                "id": "disabled",
                "function": {
                    "name": "computer",
                    "arguments": json.dumps({"action": "list", "path": str(folder)}),
                },
            })
            self.assertFalse(results[-1]["ok"])
            self.assertEqual(controller.worker.processId(), 0)
            controller.shutdown()
            repo.close()

    def test_sanitize_local_model_tool_artifacts(self):
        spec = next(t for t in TOOLS if t["function"]["name"] == "computer")
        parsed = parse_tool_arguments('```json\n{"action": "open_folder>", "path": "Downloads", "extra": 123}\n```')
        cleaned = sanitize_arguments(parsed, spec)
        self.assertEqual(cleaned, {"action": "open_folder", "path": "Downloads"})
