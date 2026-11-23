"""Resolve standard Windows user folders even when moved to another drive."""
import ctypes
import os
import uuid
from pathlib import Path

KNOWN_FOLDERS = {
    "downloads": ("374DE290-123F-4565-9164-39C4925E467B", "Downloads"),
    "desktop": ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "Desktop"),
    "área de trabalho": ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "Desktop"),
    "area de trabalho": ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "Desktop"),
    "documents": ("FDD39AD0-238F-46AF-ADB4-6C85480369C7", "Documents"),
    "documentos": ("FDD39AD0-238F-46AF-ADB4-6C85480369C7", "Documents"),
}


def known_folder(name: str) -> Path | None:
    entry = KNOWN_FOLDERS.get(name.strip().casefold())
    if not entry:
        return None
    guid_text, fallback = entry
    if os.name != "nt":
        return Path.home() / fallback
    folder_id = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(guid_text).bytes_le)
    result = ctypes.c_void_p()
    get_folder = ctypes.windll.shell32.SHGetKnownFolderPath
    get_folder.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    get_folder.restype = ctypes.c_long
    try:
        if get_folder(ctypes.byref(folder_id), 0, None, ctypes.byref(result)) != 0:
            return Path.home() / fallback
        return Path(ctypes.wstring_at(result))
    finally:
        ctypes.windll.ole32.CoTaskMemFree(result)


def downloads_folder() -> Path:
    return known_folder("downloads") or (Path.home() / "Downloads")
