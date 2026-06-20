# services/translation_memory.py — 翻译记忆库
# 模块职责：TranslationMemory 类 (SQLite + ChromaDB 双存)

import hashlib
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from config import Config
from embedding_providers import EmbeddingManager

config = Config()


class TranslationMemory:
    def __init__(self, db_path: str = config.TM_DB_PATH, chroma_client=None):
        self.db_path = db_path
        self.chroma_client = chroma_client
        self._init_db()

    @property
    def tm_collection(self):
        if self.chroma_client is None:
            return None
        try:
            return self.chroma_client.get_collection(config.TM_COLLECTION)
        except Exception:
            return self.chroma_client.create_collection(config.TM_COLLECTION)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS translation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_text TEXT NOT NULL, target_text TEXT NOT NULL,
                source_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                use_count INTEGER DEFAULT 1, context TEXT,
                source_lang TEXT DEFAULT 'en', target_lang TEXT DEFAULT 'zh'
            )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source_hash ON translation_memory(source_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_use_count ON translation_memory(use_count DESC)')
            conn.commit()

    def add(self, source_text: str, target_text: str, context: str = None,
            source_lang: str = 'en', target_lang: str = 'zh') -> bool:
        source_hash = hashlib.md5(source_text.encode('utf-8')).hexdigest()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, use_count FROM translation_memory WHERE source_hash = ?', (source_hash,))
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        'UPDATE translation_memory SET use_count = use_count + 1, updated_at = CURRENT_TIMESTAMP WHERE source_hash = ?',
                        (source_hash,))
                else:
                    cursor.execute(
                        'INSERT INTO translation_memory (source_text, target_text, source_hash, context, source_lang, target_lang) VALUES (?,?,?,?,?,?)',
                        (source_text, target_text, source_hash, context, source_lang, target_lang))
                conn.commit()
            return True
        except Exception as e:
            print(f"TM add failed: {e}")
            return False

    def search(self, query: str, threshold: float = 0.3, limit: int = 5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT source_text, target_text, use_count, context FROM translation_memory ORDER BY use_count DESC, updated_at DESC LIMIT 200')
            results = cursor.fetchall()
        matches = []
        query_words = set(query.lower().split())
        for source, target, use_count, context in results:
            source_words = set(source.lower().split())
            intersection = len(query_words & source_words)
            union = len(query_words | source_words)
            if union == 0: continue
            similarity = intersection / union
            if similarity >= threshold:
                matches.append({'source': source, 'target': target, 'similarity': similarity,
                                'use_count': use_count, 'context': context})
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches[:limit]

    def search_exact(self, source_text: str) -> Optional[Dict]:
        source_hash = hashlib.md5(source_text.encode('utf-8')).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT source_text, target_text, use_count, context FROM translation_memory WHERE source_hash = ?',
                           (source_hash,))
            row = cursor.fetchone()
        if row:
            return {'source': row[0], 'target': row[1], 'use_count': row[2], 'context': row[3]}
        return None

    def add_embedding(self, source_text: str, target_text: str, embedding: List[float],
                      context: str = None) -> bool:
        if self.chroma_client is None: return False
        try:
            collection = self.tm_collection
            if collection is None: return False
            source_hash = hashlib.md5(source_text.encode('utf-8')).hexdigest()
            collection.upsert(
                documents=[source_text], embeddings=[embedding],
                metadatas=[{"target": target_text, "source_hash": source_hash, "context": context or ""}],
                ids=[source_hash])
            return True
        except Exception as e:
            print(f"TM embedding add failed: {e}")
            return False

    def search_by_embedding(self, query_embedding: List[float], n_results: int = 5,
                            similarity_threshold: float = 0.4) -> List[Dict]:
        if self.chroma_client is None: return []
        try:
            collection = self.tm_collection
            if collection is None or collection.count() == 0: return []
            # Provider compatibility check
            try:
                meta = collection.metadata or {}
                stored = meta.get("embedding_provider", "unknown")
                current = EmbeddingManager().provider
                if current and stored != current.provider_name:
                    print(f"TM vector mismatch: stored={stored}, current={current.provider_name}")
            except Exception: pass

            results = collection.query(query_embeddings=[query_embedding], n_results=min(n_results * 2, 20))
            if not results['ids'] or not results['ids'][0]: return []

            doc_ids = results['ids'][0]
            use_count_map = {}
            if doc_ids:
                placeholders = ",".join(["?" for _ in doc_ids])
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        f'SELECT source_hash, use_count FROM translation_memory WHERE source_hash IN ({placeholders})',
                        tuple(doc_ids))
                    for row in cursor.fetchall(): use_count_map[row[0]] = row[1]

            matches = []
            for i, doc_id in enumerate(doc_ids):
                distance = results['distances'][0][i] if results['distances'] else 0
                similarity = 1.0 - min(distance, 1.0)
                if similarity < similarity_threshold: continue
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                document = results['documents'][0][i] if results['documents'] else ""
                matches.append({
                    'source': document, 'target': metadata.get('target', ''),
                    'similarity': round(similarity, 4),
                    'use_count': use_count_map.get(doc_id, 1),
                    'context': metadata.get('context', '')})
            matches.sort(key=lambda x: x['similarity'], reverse=True)
            return matches[:n_results]
        except Exception as e:
            print(f"TM vector search failed: {e}")
            return []

    def reindex_tm(self, embedding_fn) -> Dict:
        if self.chroma_client is None: return {"success": False, "error": "ChromaDB not initialized"}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT source_text, target_text, source_hash, context FROM translation_memory')
            all_records = cursor.fetchall()
        if not all_records: return {"success": True, "indexed": 0, "message": "No records to index"}
        try:
            collection = self.tm_collection
            if collection is None: return {"success": False, "error": "Cannot create vector collection"}
            try:
                existing = collection.get()
                if existing['ids']: collection.delete(ids=existing['ids'])
            except Exception: pass
            batch_size, indexed = 20, 0
            for i in range(0, len(all_records), batch_size):
                batch = all_records[i:i + batch_size]
                texts = [r[0] for r in batch]
                embeddings = embedding_fn(texts)
                ids = [r[2] for r in batch]
                metadatas = [{"target": r[1], "source_hash": r[2], "context": r[3] or ""} for r in batch]
                collection.upsert(documents=texts, embeddings=embeddings, metadatas=metadatas, ids=ids)
                indexed += len(batch)
            try:
                current = EmbeddingManager().provider
                if current:
                    collection.modify(metadata={
                        "embedding_provider": current.provider_name,
                        "embedding_model": current.model_name,
                        "indexed_at": datetime.now().isoformat()})
            except Exception as e: print(f"TM metadata write failed: {e}")
            return {"success": True, "indexed": indexed, "message": f"Reindexed {indexed} records"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, source_text, target_text, use_count, created_at, updated_at, context FROM translation_memory ORDER BY use_count DESC, updated_at DESC LIMIT ? OFFSET ?',
                (limit, offset))
            results = cursor.fetchall()
        return [{'id': r[0], 'source': r[1], 'target': r[2], 'use_count': r[3],
                 'created_at': r[4], 'updated_at': r[5], 'context': r[6]} for r in results]

    def delete(self, tm_id: int) -> bool:
        source_hash = None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT source_hash FROM translation_memory WHERE id = ?', (tm_id,))
            row = cursor.fetchone()
            if row: source_hash = row[0]
            cursor.execute('DELETE FROM translation_memory WHERE id = ?', (tm_id,))
            conn.commit()
            affected = cursor.rowcount
        if affected > 0 and source_hash and self.chroma_client:
            try:
                collection = self.tm_collection
                if collection: collection.delete(ids=[source_hash])
            except Exception as e: print(f"TM vector delete failed: {e}")
        return affected > 0

    def clear(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM translation_memory')
            conn.commit()
        if self.chroma_client:
            try:
                self.chroma_client.delete_collection(config.TM_COLLECTION)
            except Exception as e:
                print(f"TM collection clear failed: {e}")
                return False
        return True

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM translation_memory')
            return cursor.fetchone()[0]


# 单例
tm_instance = TranslationMemory(chroma_client=None)  # will be set by app init
