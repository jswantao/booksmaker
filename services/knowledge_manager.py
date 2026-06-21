# services/knowledge_manager.py — 知识库元数据管理
# 模块职责：KnowledgeBaseManager 类 (SQLite + ChromaDB)

import sqlite3
import uuid
from typing import List, Dict, Optional
from config import Config

config = Config()


class KnowledgeBaseManager:
    def __init__(self, db_path: str, chroma_client):
        self.db_path = db_path
        self.chroma_client = chroma_client
        self._init_db()

    def _execute(self, sql: str, params=()):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor.fetchall() if cursor.description else []

    def _execute_one(self, sql: str, params=()):
        rows = self._execute(sql, params)
        return rows[0] if rows else None

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS kb_groups (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            c.execute('''CREATE TABLE IF NOT EXISTS knowledge_bases (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
                collection_name TEXT NOT NULL UNIQUE, embedding_model TEXT DEFAULT '',
                group_id TEXT, document_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES kb_groups(id) ON DELETE SET NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS agent_kb_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name TEXT NOT NULL, kb_id TEXT NOT NULL,
                is_default INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                UNIQUE(agent_name, kb_id))''')
            conn.commit()

    # ---- Group CRUD ----
    def create_group(self, name: str, description: str = "") -> Dict:
        gid = uuid.uuid4().hex[:12]
        self._execute("INSERT INTO kb_groups (id, name, description) VALUES (?,?,?)", (gid, name, description))
        return self.get_group(gid)

    def update_group(self, group_id: str, name=None, description=None) -> bool:
        fields, vals = [], []
        if name is not None: fields.append("name=?"); vals.append(name)
        if description is not None: fields.append("description=?"); vals.append(description)
        if not fields: return False
        fields.append("updated_at=CURRENT_TIMESTAMP"); vals.append(group_id)
        self._execute(f"UPDATE kb_groups SET {', '.join(fields)} WHERE id=?", tuple(vals))
        return True

    def delete_group(self, group_id: str) -> bool:
        self._execute("UPDATE knowledge_bases SET group_id=NULL WHERE group_id=?", (group_id,))
        self._execute("DELETE FROM kb_groups WHERE id=?", (group_id,))
        return True

    def get_all_groups(self) -> List[Dict]:
        rows = self._execute("SELECT id, name, description, created_at, updated_at FROM kb_groups ORDER BY name")
        return [{"id": r[0], "name": r[1], "description": r[2], "created_at": r[3], "updated_at": r[4]} for r in
                rows]

    def get_group(self, group_id: str) -> Optional[Dict]:
        r = self._execute_one(
            "SELECT id, name, description, created_at, updated_at FROM kb_groups WHERE id=?", (group_id,))
        return {"id": r[0], "name": r[1], "description": r[2], "created_at": r[3], "updated_at": r[4]} if r else None

    # ---- KB CRUD ----
    def create_kb(self, name: str, description: str = "", embedding_model: str = "",
                  group_id: str = None, collection_name: str = None) -> Dict:
        kid = uuid.uuid4().hex[:12]
        col_name = collection_name or f"kb_{uuid.uuid4().hex[:12]}"
        try:
            self.chroma_client.get_collection(col_name)
        except Exception:
            self.chroma_client.create_collection(col_name)
        self._execute(
            "INSERT INTO knowledge_bases (id, name, description, collection_name, embedding_model, group_id) VALUES (?,?,?,?,?,?)",
            (kid, name, description, col_name, embedding_model, group_id))
        return self.get_kb(kid)

    def update_kb(self, kb_id: str, name=None, description=None, group_id=None, embedding_model=None) -> bool:
        fields, vals = [], []
        if name is not None: fields.append("name=?"); vals.append(name)
        if description is not None: fields.append("description=?"); vals.append(description)
        if group_id is not None: fields.append("group_id=?"); vals.append(group_id)
        if embedding_model is not None: fields.append("embedding_model=?"); vals.append(embedding_model)
        if not fields: return False
        fields.append("updated_at=CURRENT_TIMESTAMP"); vals.append(kb_id)
        self._execute(f"UPDATE knowledge_bases SET {', '.join(fields)} WHERE id=?", tuple(vals))
        return True

    def delete_kb(self, kb_id: str) -> bool:
        kb = self.get_kb(kb_id)
        if not kb: return False
        try:
            self.chroma_client.delete_collection(kb["collection_name"])
        except Exception as e:
            print(f"ChromaDB collection delete failed: {e}")
        self._execute("DELETE FROM agent_kb_assignments WHERE kb_id=?", (kb_id,))
        self._execute("DELETE FROM knowledge_bases WHERE id=?", (kb_id,))
        return True

    def get_all_kbs(self, group_id: str = None) -> List[Dict]:
        if group_id:
            rows = self._execute(
                "SELECT id, name, description, collection_name, embedding_model, group_id, document_count, created_at, updated_at FROM knowledge_bases WHERE group_id=? ORDER BY name",
                (group_id,))
        else:
            rows = self._execute(
                "SELECT id, name, description, collection_name, embedding_model, group_id, document_count, created_at, updated_at FROM knowledge_bases ORDER BY name")
        return [self._row_to_kb(r) for r in rows]

    def get_kb(self, kb_id: str) -> Optional[Dict]:
        r = self._execute_one(
            "SELECT id, name, description, collection_name, embedding_model, group_id, document_count, created_at, updated_at FROM knowledge_bases WHERE id=?",
            (kb_id,))
        return self._row_to_kb(r) if r else None

    def get_kbs_by_ids(self, kb_ids: List[str]) -> List[Dict]:
        if not kb_ids: return []
        placeholders = ",".join(["?" for _ in kb_ids])
        rows = self._execute(
            f"SELECT id, name, description, collection_name, embedding_model, group_id, document_count, created_at, updated_at FROM knowledge_bases WHERE id IN ({placeholders}) ORDER BY name",
            tuple(kb_ids))
        return [self._row_to_kb(r) for r in rows]

    def get_kbs_by_group(self, group_id: str) -> List[Dict]:
        return self.get_all_kbs(group_id=group_id)

    def _row_to_kb(self, r) -> Dict:
        if not r: return None
        return {"id": r[0], "name": r[1], "description": r[2], "collection_name": r[3],
                "embedding_model": r[4], "group_id": r[5], "document_count": r[6],
                "created_at": r[7], "updated_at": r[8]}

    def update_document_count(self, kb_id: str, delta: int = 0):
        if delta:
            self._execute("UPDATE knowledge_bases SET document_count=MAX(0, document_count+?) WHERE id=?",
                          (delta, kb_id))
        else:
            kb = self.get_kb(kb_id)
            if kb:
                try:
                    col = self.chroma_client.get_collection(kb["collection_name"])
                    self._execute("UPDATE knowledge_bases SET document_count=? WHERE id=?", (col.count(), kb_id))
                except Exception: pass

    # ---- Agent-KB ----
    def assign_kb_to_agent(self, agent_name: str, kb_id: str, is_default: bool = False) -> bool:
        try:
            if is_default: self._execute("UPDATE agent_kb_assignments SET is_default=0 WHERE agent_name=?",
                                         (agent_name,))
            self._execute("INSERT OR REPLACE INTO agent_kb_assignments (agent_name, kb_id, is_default) VALUES (?,?,?)",
                          (agent_name, kb_id, 1 if is_default else 0))
            return True
        except Exception as e:
            print(f"Agent-KB assign failed: {e}"); return False

    def unassign_kb_from_agent(self, agent_name: str, kb_id: str) -> bool:
        self._execute("DELETE FROM agent_kb_assignments WHERE agent_name=? AND kb_id=?", (agent_name, kb_id))
        return True

    def get_agent_kbs(self, agent_name: str) -> List[Dict]:
        rows = self._execute(
            "SELECT a.kb_id, a.is_default, k.name, k.description, k.collection_name, k.embedding_model, k.group_id, k.document_count FROM agent_kb_assignments a JOIN knowledge_bases k ON a.kb_id=k.id WHERE a.agent_name=? ORDER BY a.is_default DESC, k.name",
            (agent_name,))
        return [{"kb_id": r[0], "is_default": bool(r[1]), "name": r[2], "description": r[3],
                 "collection_name": r[4], "embedding_model": r[5], "group_id": r[6], "document_count": r[7]} for r in
                rows]

    def get_agent_default_kb_ids(self, agent_name: str) -> List[str]:
        rows = self._execute("SELECT kb_id FROM agent_kb_assignments WHERE agent_name=? AND is_default=1",
                             (agent_name,))
        if not rows: rows = self._execute("SELECT kb_id FROM agent_kb_assignments WHERE agent_name=?", (agent_name,))
        return [r[0] for r in rows]


# 单例
kb_manager = KnowledgeBaseManager(config.KB_DB_PATH, chroma_client=None)
