"""Local SQLite repository. Every write is committed before returning."""
import json
import os
import sqlite3
from pathlib import Path
from gamenext.domain.models import Message, new_id


def default_cpu_threads() -> int:
    count = os.cpu_count() or 4
    return max(2, min(8, count // 2 if count >= 4 else count))


def default_batch_threads() -> int:
    return max(2, os.cpu_count() or 4)


class Repository:
    SCHEMA_PREFS_VERSION = 4

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                updated TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES
                conversations(id) ON DELETE CASCADE, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tool_audit (id INTEGER PRIMARY KEY, tool TEXT, success INTEGER, elapsed REAL, created TEXT DEFAULT CURRENT_TIMESTAMP);
            PRAGMA user_version=1;
        """)
        for mid, payload in self.db.execute("SELECT id,payload FROM messages").fetchall():
            data = json.loads(payload)
            if data.get("status") == "processando":
                data["status"] = "interrompido"
                self.db.execute("UPDATE messages SET payload=? WHERE id=?", (json.dumps(data, ensure_ascii=False), mid))
        self.db.commit()
        self._migrate_legacy_limits()

    def _migrate_legacy_limits(self):
        """Upgrade restrictive v0.3.x caps once so local models run freely."""
        version = self.preference("settings_schema_version", 0)
        if version >= self.SCHEMA_PREFS_VERSION:
            return
        existing_keys = {row[0] for row in self.db.execute("SELECT key FROM preferences").fetchall()}
        if existing_keys:
            if "vram" in existing_keys and 0 < (self.preference("vram", 0) or 0) <= 6500:
                self.set_preference("vram", 0)
            if "ram" in existing_keys and 0 < (self.preference("ram", 0) or 0) <= 13000:
                self.set_preference("ram", 0)
            if "context" in existing_keys and (self.preference("context", 0) or 0) < 4096:
                self.set_preference("context", 8192)
            if "batch" in existing_keys and (self.preference("batch", 0) or 0) < 256:
                self.set_preference("batch", 512)
            if "ubatch" in existing_keys and (self.preference("ubatch", 0) or 0) < 256:
                self.set_preference("ubatch", 256)
            if "threads" in existing_keys and (self.preference("threads", 0) or 0) <= 3:
                self.set_preference("threads", default_cpu_threads())
            if "threads_batch" not in existing_keys:
                self.set_preference("threads_batch", default_batch_threads())
            if self.preference("reasoning") == "Baixo":
                self.set_preference("reasoning", "Livre")
                composer = self.preference("composer", [0, 3, 0])
                if isinstance(composer, list) and len(composer) >= 2:
                    composer[1] = 3
                    self.set_preference("composer", composer)
            if "tool_ask_changes" in existing_keys and self.preference("tool_ask_changes") is True:
                self.set_preference("tool_ask_changes", False)
            if "gpu_mode" not in existing_keys:
                self.set_preference("gpu_mode", "auto")
        self.set_preference("settings_schema_version", self.SCHEMA_PREFS_VERSION)

    def create(self, title: str = "Nova conversa") -> str:
        cid = new_id()
        with self.db:
            self.db.execute("INSERT INTO conversations(id,title) VALUES (?,?)", (cid, title))
        return cid

    def list_conversations(self, search: str = "") -> list:
        return self.db.execute(
            "SELECT id,title FROM conversations WHERE title LIKE ? ORDER BY updated DESC, rowid DESC",
            (f"%{search}%",),
        ).fetchall()

    def rename(self, cid: str, title: str):
        with self.db:
            self.db.execute("UPDATE conversations SET title=?,updated=CURRENT_TIMESTAMP WHERE id=?", (title, cid))

    def delete(self, cid: str):
        with self.db:
            self.db.execute("DELETE FROM conversations WHERE id=?", (cid,))

    def save_message(self, cid: str, message: Message):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO messages VALUES (?,?,?)", (message.id, cid, json.dumps(message.serialize(), ensure_ascii=False)))
            self.db.execute("UPDATE conversations SET updated=CURRENT_TIMESTAMP WHERE id=?", (cid,))

    def messages(self, cid: str) -> list[Message]:
        return [Message(**json.loads(row[0])) for row in self.db.execute(
            "SELECT payload FROM messages WHERE conversation_id=? ORDER BY rowid", (cid,))]

    def preference(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_preference(self, key: str, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", (key, json.dumps(value)))

    def close(self):
        self.db.close()

    def audit_tool(self, tool: str, success: bool, elapsed: float):
        with self.db:
            self.db.execute("INSERT INTO tool_audit(tool,success,elapsed) VALUES (?,?,?)", (tool, success, elapsed))
