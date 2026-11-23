"""Meaningful MVP checks using Qt's real event loop and isolated local storage."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from gamenext.bootstrap import build_window
from gamenext.domain.models import Message
from gamenext.infrastructure.storage import Repository
from gamenext.presentation.theme import STYLE


class MvpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.window = build_window(self.directory, demo=True)
        self.window.show()
        QTest.qWait(30)

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        import logging
        logger = logging.getLogger("gamenext")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        self.temp.cleanup()

    def test_keyboard_stream_cancel_and_restart_persistence(self):
        w = self.window
        w.composer.input.setPlainText("processando um projeto Python")
        QTest.keyClick(w.composer.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertIn("\n", w.composer.input.toPlainText())
        QTest.keyClick(w.composer.input, Qt.Key.Key_Return)
        QTest.qWait(100)
        self.assertTrue(w.controller.active)
        cid = w.current_id
        w.controller.stop()
        self.assertFalse(w.controller.active)
        records = w.repository.messages(cid)
        self.assertEqual(records[0].content, "processando um projeto Python")
        self.assertTrue(records[1].content)
        self.assertEqual(records[1].status, "cancelado")
        w.close()
        self.window = build_window(self.directory, demo=True)
        self.assertEqual(self.window.current_id, cid)
        self.assertEqual(self.window.repository.messages(cid)[0].content, records[0].content)

    def test_navigation_resize_and_task_pause(self):
        w = self.window
        w.navigate(2)
        self.assertEqual(w.pages.currentWidget(), w.settings)
        w.settings.controls["context"].setValue(8192)
        w.settings.save()
        self.assertEqual(w.repository.preference("context"), 8192)
        w.navigate(0)
        w.resize(1440, 900)
        w.task_requested = True
        w.tasks.start("Plano demonstrativo")
        w.update_tasks_visibility()
        QTest.qWait(50)
        self.assertTrue(w.tasks.isVisible())
        w.tasks.toggle()
        previous = w.tasks.plan.completed
        QTest.qWait(60)
        self.assertEqual(w.tasks.plan.completed, previous)
        w.resize(960, 640)
        QTest.qWait(50)
        self.assertFalse(w.tasks.isVisible())
        self.assertLessEqual(w.composer.width(), w.chat.width())
        w.toggle_sidebar()
        self.assertEqual(w.sidebar.width(), 48)
        w.tasks.cancel_plan()
        self.assertEqual(w.tasks.plan.status, "cancelada")

    def test_foreign_key_delete_and_interrupted_recovery(self):
        path = self.directory / "isolated.sqlite3"
        repo = Repository(path)
        cid = repo.create("Teste")
        repo.save_message(cid, Message("assistant", "Texto processando permanece", status="processando"))
        repo.close()
        repo = Repository(path)
        self.assertEqual(repo.messages(cid)[0].status, "interrompido")
        self.assertEqual(repo.messages(cid)[0].content, "Texto processando permanece")
        repo.delete(cid)
        self.assertEqual(repo.messages(cid), [])
        repo.close()

    def test_code_expansion_and_complete_stream(self):
        w = self.window
        w.fill_prompt("código Python")
        w.send()
        QTest.qWait(1800)
        self.assertFalse(w.controller.active)
        message = w.repository.messages(w.current_id)[-1]
        self.assertEqual(message.status, "concluído")
        self.assertIn("```python", message.content)
        self.assertGreater(w.streaming_view.layout_.count(), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
