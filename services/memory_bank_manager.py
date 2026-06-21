# services/memory_bank_manager.py — 记忆库管理器
# 按书名隔离记忆库实例，支持全局术语库，缓存已加载实例

import os
import re
import threading
from typing import Optional, Dict
from services.memory_bank import MemoryBank


class MemoryBankManager:
    """记忆库管理器 - 按书名隔离，缓存实例"""

    BASE_DIR = "memory_banks"

    def __init__(self):
        self._banks: Dict[str, MemoryBank] = {}
        self._global_bank: Optional[MemoryBank] = None
        self._lock = threading.Lock()

    def _sanitize_name(self, name: str) -> str:
        """清理文件名中的非法字符"""
        return re.sub(r'[\\/:*?"<>|]', '_', name).strip()

    def _get_bank_path(self, book_name: str) -> str:
        """生成记忆库文件路径"""
        safe_name = self._sanitize_name(book_name)
        bank_dir = os.path.join(self.BASE_DIR, safe_name)
        os.makedirs(bank_dir, exist_ok=True)
        return os.path.join(bank_dir, "memory.json")

    def _get_global_path(self) -> str:
        """全局记忆库路径"""
        global_dir = os.path.join(self.BASE_DIR, "_global")
        os.makedirs(global_dir, exist_ok=True)
        return os.path.join(global_dir, "memory.json")

    def get_bank(self, book_name: Optional[str] = None) -> MemoryBank:
        """
        获取记忆库实例：
        - 有书名 → 返回该书专属记忆库（缓存）
        - 无书名 → 返回全局记忆库（仅术语，不存翻译对）
        """
        with self._lock:
            if not book_name:
                if self._global_bank is None:
                    self._global_bank = MemoryBank(self._get_global_path())
                    self._global_bank.data["project"] = "_global"
                return self._global_bank

            if book_name not in self._banks:
                path = self._get_bank_path(book_name)
                bank = MemoryBank(path)
                bank.data["project"] = book_name
                # 新记忆库自动导入种子术语表
                if not bank.data.get("terminology"):
                    from services.translate_optimizer import SEED_GLOSSARY
                    bank.data["terminology"] = dict(SEED_GLOSSARY)
                    bank._dirty = True
                    bank._save()
                self._banks[book_name] = bank
            return self._banks[book_name]

    def load_from_path(self, file_path: str, project: str = "") -> MemoryBank:
        """
        通过文件路径直接加载记忆库（供 pipeline 使用）。
        同一路径会缓存复用，避免重复实例。
        """
        with self._lock:
            if file_path not in self._banks:
                bank = MemoryBank(file_path)
                if project:
                    bank.data["project"] = project
                self._banks[file_path] = bank
            return self._banks[file_path]

    def get_all_bank_names(self) -> list:
        """列出所有已有记忆库的书名"""
        if not os.path.exists(self.BASE_DIR):
            return []
        names = []
        for d in os.listdir(self.BASE_DIR):
            if d.startswith("_"):
                continue
            meta_path = os.path.join(self.BASE_DIR, d, "memory.json")
            if os.path.exists(meta_path):
                names.append(d)
        return sorted(names)

    def flush_all(self):
        """强制刷盘所有已加载的记忆库"""
        with self._lock:
            for bank in self._banks.values():
                bank.flush()
            if self._global_bank:
                self._global_bank.flush()

    def get_merged_terminology(self, book_name: Optional[str] = None) -> Dict[str, str]:
        """获取合并后的术语表：全局术语 + 书籍专属术语"""
        merged = {}
        # 全局术语（低优先级）
        if self._global_bank:
            merged.update(self._global_bank.get_terminology())
        # 书籍术语（高优先级，覆盖全局）
        if book_name and book_name in self._banks:
            merged.update(self._banks[book_name].get_terminology())
        return merged

    def promote_term_to_global(self, en_term: str, zh_term: str):
        """将术语提升为全局术语（跨书共享）"""
        if self._global_bank is None:
            self._global_bank = MemoryBank(self._get_global_path())
        self._global_bank.add_term(en_term, zh_term)


# 全局单例
memory_bank_manager = MemoryBankManager()
