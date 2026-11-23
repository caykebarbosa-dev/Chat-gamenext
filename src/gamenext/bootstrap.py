"""Composition root and rotating local application logs."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from gamenext.infrastructure.storage import Repository
from gamenext.presentation.window import MainWindow


def build_window(data_dir: Path | None = None, demo: bool = False) -> MainWindow:
    directory = data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GameNext"
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gamenext")
    if not logger.handlers:
        handler = RotatingFileHandler(directory / "gamenext.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.info("GameNext started")
    return MainWindow(Repository(directory / "gamenext.sqlite3"), directory, demo=demo)
