# services/memory_bank_manager.py — Memory Bank Manager v3
# per-book isolated, concise, read-only for general translation

import os
import re
import threading
from typing import Optional, Dict
from services.memory_bank import MemoryBank
from config import PROJECT_ROOT

class MemoryBankManager:
    """Per-book MemoryBank, concise by design"""

    BASE_DIR = str(PROJECT_ROOT / "memory_banks")

    def __init__(self):
        self._banks: Dict[str, MemoryBank] = {}
        self._lock = threading.Lock()

    def _sanitize_name(self, name: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', '_', name).strip()[:80]

    def _get_bank_path(self, book_title: str) -> str:
        safe = self._sanitize_name(book_title)
        bank_dir = os.path.join(self.BASE_DIR, safe)
        os.makedirs(bank_dir, exist_ok=True)
        return os.path.join(bank_dir, "memory.json")

    def get_bank(self, book_title: Optional[str] = None) -> MemoryBank:
        """
        Get memory bank:
        - book_title provided -> per-book read/write bank (auto-construct)
        - no book_title -> ephemeral read-only bank, NO storage of translations
        """
        with self._lock:
            if not book_title or not book_title.strip():
                # General translation: read-only, no persistence
                # Return a dummy in-memory bank
                return MemoryBank(
                    file_path=os.path.join(self.BASE_DIR, "_general", "memory.ephemeral.json"),
                    book_title="",
                    read_only=True
                )
            title = book_title.strip()
            if title not in self._banks:
                path = self._get_bank_path(title)
                bank = MemoryBank(path, book_title=title, read_only=False)
                self._banks[title] = bank
            return self._banks[title]

    def get_readonly_snapshot(self, book_title: Optional[str] = None) -> MemoryBank:
        """For general translation: read-only snapshot, never writes"""
        return self.get_bank(book_title)

    def get_writable_global_bank(self) -> MemoryBank:
        """Return a writable bank for shared terminology operations.
        Distinct from get_bank(None) which returns a read-only ephemeral bank
        to prevent accidental writes during general translation."""
        with self._lock:
            global_key = "__global_terminology__"
            if global_key not in self._banks:
                path = os.path.join(self.BASE_DIR, "_shared", "terminology.json")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                self._banks[global_key] = MemoryBank(path, book_title="", read_only=False)
            return self._banks[global_key]

    def list_books(self) -> list:
        if not os.path.exists(self.BASE_DIR):
            return []
        names = []
        for d in os.listdir(self.BASE_DIR):
            if d.startswith("_"): continue
            meta = os.path.join(self.BASE_DIR, d, "memory.json")
            if os.path.exists(meta):
                names.append(d)
        return sorted(names)

    def flush_all(self):
        with self._lock:
            for bank in self._banks.values():
                bank.flush()

# singleton
memory_bank_manager = MemoryBankManager()
