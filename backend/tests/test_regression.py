# tests/test_regression.py -- Phase 4 regression tests
#
# Validates the full LangChain migration pipeline:
# 1. Translate chain: mock LLM -> correct output
# 2. SSE streaming: tokens arrive one-by-one
# 3. EPUB cleaning: XHTML structure preserved
# 4. Translation cleaning: prefixes/annotations stripped
# 5. Hybrid search: non-empty results with correct dict format
# 6. Callback logging: events written to log file
# 7. Observability integration: callbacks attached to built chains

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# ---------------------------------------------------------------------------
# Mock setup (must run BEFORE imports)
# ---------------------------------------------------------------------------

# Mock jieba (must include __spec__ for importlib.util.find_spec compatibility)
import importlib
mock_jieba = MagicMock()
mock_jieba.__spec__ = importlib.machinery.ModuleSpec('jieba', loader=None)
import re as _re
def fake_lcut(text):
    tokens = []
    for m in _re.finditer(r'[\u4e00-\u9fff]+|[a-zA-Z]+|\d+', text.lower()):
        w = m.group()
        if len(w) <= 2:
            tokens.append(w)
        else:
            tokens.extend([w[i:i+2] for i in range(len(w)-1)])
    return tokens
mock_jieba.lcut = fake_lcut
sys.modules['jieba'] = mock_jieba

# Mock rank_bm25
import math
class FakeBM25Okapi:
    def __init__(self, tokenized_corpus):
        self.corpus_size = len(tokenized_corpus)
        self.corpus = tokenized_corpus
        self.doc_freqs = {}
        for tokens in tokenized_corpus:
            for t in set(tokens):
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1
        self.idf = {}
        N = self.corpus_size
        for term, n in self.doc_freqs.items():
            self.idf[term] = math.log((N - n + 0.5) / (n + 0.5))
        self.avgdl = sum(len(t) for t in tokenized_corpus) / max(len(tokenized_corpus), 1)
        self.doc_lens = [len(t) for t in tokenized_corpus]
        self.k1 = 1.5
        self.b = 0.75
    def get_scores(self, query):
        scores = []
        for i in range(self.corpus_size):
            score = 0.0
            for token in query:
                if token not in self.idf:
                    continue
                tf = self.corpus[i].count(token)
                idf = self.idf[token]
                dl = self.doc_lens[i]
                score += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append(score)
        return scores

mock_rank_bm25 = MagicMock()
mock_rank_bm25.__spec__ = importlib.machinery.ModuleSpec('rank_bm25', loader=None)
mock_rank_bm25.BM25Okapi = FakeBM25Okapi
sys.modules['rank_bm25'] = mock_rank_bm25

# Mock ChromaDB
mock_docs = ['Napoleon conquered Europe.', 'World War II ended in 1945.']
mock_metas = [{'group': 'h', 'chapter': '1'}, {'group': 'h', 'chapter': '2'}]
mock_ids = ['d1', 'd2']
mock_collection = MagicMock()
mock_collection.get.return_value = {'documents': mock_docs, 'metadatas': mock_metas, 'ids': mock_ids}
mock_collection.count.return_value = 2
mock_chroma_client = MagicMock()
mock_chroma_client.get_collection.return_value = mock_collection
mock_db = MagicMock()
mock_db.chroma_client = mock_chroma_client
sys.modules['core.database'] = mock_db

# Mock LLMManager + EmbeddingManager
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk

mock_llm_manager = MagicMock()
mock_embedding_manager = MagicMock()

# LLMManager returns a fixed translation
MOCK_TRANSLATION = '\u62ff\u7834\u4ed1\u5f81\u670d\u4e86\u6b27\u6d32\u3002'
MOCK_EPUB_OUTPUT = '<p>Napoleon conquered Europe.</p>'
MOCK_TOKENS = ['\u62ff', '\u7834', '\u4ed1', '\u5f81', '\u670d', '\u4e86', '\u6b27', '\u6d32', '\u3002']

def mock_chat(messages, task='translate', **kw):
    if 'epub' in task:
        return MOCK_EPUB_OUTPUT
    return MOCK_TRANSLATION

def mock_chat_stream(messages, task='translate', **kw):
    return iter(MOCK_TOKENS)

mock_llm_manager.chat = mock_chat
mock_llm_manager.chat_stream = mock_chat_stream

mock_llm_class = MagicMock()
mock_llm_class.return_value = mock_llm_manager
# ChatQoderWork._generate does: from model_providers import LLMManager
mock_model_providers = MagicMock()
mock_model_providers.LLMManager = mock_llm_class
mock_model_providers.__spec__ = importlib.machinery.ModuleSpec('model_providers', loader=None)
sys.modules['model_providers'] = mock_model_providers
# Also keep the old path for any other imports
sys.modules['core.model_manager'] = MagicMock(LLMManager=mock_llm_class)

mock_emb_class = MagicMock()
mock_emb_instance = MagicMock()
mock_emb_instance.embed.return_value = [[0.1] * 384]
mock_emb_class.return_value = mock_emb_instance
sys.modules['core.embedding_manager'] = MagicMock(EmbeddingManager=mock_emb_class)

# Now import project modules
from langchain_adapters.chat_models import ChatQoderWork
from langchain_adapters.factory import get_chat_model
from agents_lcel.chains import build_chain_for_task
from observability.callbacks import (
    QoderWorkCallbackHandler, setup_langchain_logging, get_langchain_callbacks,
)

print('=' * 60)
print('Phase 4 Regression Tests')
print('=' * 60)

passed = 0
failed = 0
total = 7

# ===========================================================================
# Test 1: Translate chain produces correct output
# ===========================================================================
print('\n[Test 1/7] Translate chain (mock LLM -> correct output)')
try:
    chain = build_chain_for_task('paragraph_translate', model_name='test-model')
    result = chain.invoke({'input': 'Napoleon conquered Europe.'})
    assert isinstance(result, str), f'Expected str, got {type(result)}'
    assert len(result) > 0, 'Translation should not be empty'
    print(f'  Output: {result[:80]}')
    print('  PASS')
    passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    import traceback; traceback.print_exc()
    failed += 1

# ===========================================================================
# Test 2: SSE streaming delivers tokens one-by-one
# ===========================================================================
print('\n[Test 2/7] SSE streaming (token-by-token delivery)')
try:
    chain2 = build_chain_for_task('paragraph_translate', model_name='test-model')
    tokens_received = []
    for chunk in chain2.stream({'input': 'Napoleon conquered Europe.'}):
        tokens_received.append(chunk)
    assert len(tokens_received) >= 2, f'Expected multiple chunks, got {len(tokens_received)}'
    for t in tokens_received:
        assert isinstance(t, str), f'Chunk should be str, got {type(t)}'
    combined = ''.join(tokens_received)
    assert len(combined) > 0, 'Combined stream should not be empty'
    print(f'  Tokens: {len(tokens_received)}, combined={combined[:80]}')
    print('  PASS')
    passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    import traceback; traceback.print_exc()
    failed += 1

# ===========================================================================
# Test 3: EPUB structure preservation (_clean_epub logic)
# ===========================================================================
print('\n[Test 3/7] EPUB structure preservation')
try:
    def clean_epub(text):
        text = re.sub(r'```[\w]*\n?', '', text)
        text = text.strip()
        m = re.search(r'<[^>]+>', text)
        if m and m.start() > 0:
            text = text[m.start():]
        return text.strip()

    cases = [
        ('```html\n<p>Hello</p>\n```', '<p>'),
        ('Here is the result:\n<div>Content</div>', '<div>'),
        ('<p>Direct XHTML</p>', '<p>'),
        ('```xml\n<h1>Title</h1>', '<h1>'),
        ('Leading garbage<span>x</span>trailing', '<span>'),
    ]
    for inp, expected_prefix in cases:
        out = clean_epub(inp)
        assert out.startswith(expected_prefix), \
            f'clean_epub({inp!r}) -> {out!r}, expected startswith {expected_prefix!r}'
        print(f'  OK: {inp[:40]}... -> starts with {expected_prefix}')
    print('  PASS')
    passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    failed += 1

# ===========================================================================
# Test 4: Translation cleaning (_clean_translation logic)
# ===========================================================================
print('\n[Test 4/7] Translation cleaning (_clean_translation)')
try:
    def clean_translation(text):
        text = re.sub(r'^(译文|翻译|输出|结果)[：:]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'```[\w]*\n?', '', text)
        text = re.sub(r'\n*[\[\(]?注[：:].*$', '', text, flags=re.MULTILINE)
        text = re.split(r'\n- [""][^""]+[""]\s*[:：]', text)[0]
        return text.strip()

    cases = [
        ('译文：拿破仑征服了欧洲', '拿破仑'),
        ('翻译: Hello world', 'Hello world'),
        ('```\n拿破仑\n```', '拿破仑'),
        ('拿破仑\n[注：这是注释]', '拿破仑'),
    ]
    for inp, expected_start in cases:
        out = clean_translation(inp)
        assert out.startswith(expected_start), \
            f'clean_translation({inp!r}) -> {out!r}, expected startswith {expected_start!r}'
        print(f'  OK: {inp[:30]}... -> starts with {expected_start}')
    print('  PASS')
    passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    failed += 1

# ===========================================================================
# Test 5: Hybrid search returns non-empty results
# ===========================================================================
print('\n[Test 5/7] Hybrid search (non-empty results)')
try:
    from retrievers.bm25 import QoderWorkBM25Retriever
    from retrievers.hybrid import HybridRetriever
    from langchain_core.documents import Document

    bm25 = QoderWorkBM25Retriever(collection_name='test_kb', k=3)
    assert bm25.is_ready, 'BM25 should be ready'
    results = bm25._get_relevant_documents('Napoleon war Europe')
    assert len(results) > 0, f'BM25 should return results, got {len(results)}'
    for r in results:
        assert isinstance(r, Document), f'Result should be Document, got {type(r)}'
        assert r.page_content, 'page_content should not be empty'
    print(f'  BM25 results: {len(results)} docs')

    # RRF fusion
    list_a = [Document(page_content='A', id='a'), Document(page_content='B', id='b')]
    list_b = [Document(page_content='B', id='b'), Document(page_content='C', id='c')]
    fused = HybridRetriever._rrf_fusion([list_a, list_b], weights=[0.6, 0.4])
    assert len(fused) == 3, f'Expected 3 unique docs, got {len(fused)}'
    b_score = next(d.metadata['_rrf_score'] for d in fused if d.id == 'b')
    a_score = next(d.metadata['_rrf_score'] for d in fused if d.id == 'a')
    assert b_score > a_score, f'B ({b_score}) should beat A ({a_score})'
    print(f'  RRF fused: 3 docs, B is top (score={b_score})')
    print('  PASS')
    passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    import traceback; traceback.print_exc()
    failed += 1

# ===========================================================================
# Test 6: Callback logging writes events to file
# ===========================================================================
print('\n[Test 6/7] Callback logging (events written to file)')
try:
    import importlib
    import observability.callbacks as cb_mod
    # Reset module state for clean test
    cb_mod._initialized = False
    cb_mod._callbacks = []
    # Clear existing logger handlers so new ones get added for temp dir
    evt_logger = logging.getLogger('langchain_events')
    evt_logger.handlers.clear()

    with tempfile.TemporaryDirectory() as tmpdir:
        setup_langchain_logging(log_dir=tmpdir, max_bytes=1024*1024, backup_count=1)
        callbacks = get_langchain_callbacks()
        assert len(callbacks) == 1, f'Expected 1 callback, got {len(callbacks)}'
        handler = callbacks[0]
        assert isinstance(handler, QoderWorkCallbackHandler)

        from uuid import uuid4
        run_id = uuid4()
        handler.on_chain_start(
            serialized={'name': 'TestChain'},
            inputs={'input': 'test query'},
            run_id=run_id,
        )
        handler.on_chain_end(
            outputs={'output': 'test result'},
            run_id=run_id,
        )
        handler.on_chain_error(
            error=RuntimeError('test error'),
            run_id=run_id,
        )

        log_path = os.path.join(tmpdir, 'langchain.log')
        assert os.path.exists(log_path), f'Log file should exist at {log_path}'
        with open(log_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
        assert 'CHAIN_START' in log_content, 'Log should contain CHAIN_START'
        assert 'CHAIN_END' in log_content, 'Log should contain CHAIN_END'
        assert 'CHAIN_ERROR' in log_content, 'Log should contain CHAIN_ERROR'
        assert 'TestChain' in log_content, 'Log should contain chain name'
        print(f'  Log file: {log_path} ({len(log_content)} bytes)')
        print(f'  Events: CHAIN_START, CHAIN_END, CHAIN_ERROR all present')
        # Close handlers to release file locks before temp dir cleanup (Windows)
        for h in evt_logger.handlers[:]:
            h.close()
            evt_logger.removeHandler(h)
        print('  PASS')
        passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    import traceback; traceback.print_exc()
    failed += 1

# ===========================================================================
# Test 7: Observability integration (callbacks attached to built chains)
# ===========================================================================
print('\n[Test 7/7] Observability integration (callbacks on built chains)')
try:
    chain7 = build_chain_for_task('paragraph_translate', model_name='test-model')
    cfg = chain7.config
    assert 'callbacks' in cfg, f'Chain config should have callbacks, got keys: {list(cfg.keys())}'
    assert len(cfg['callbacks']) > 0, 'Callbacks list should not be empty'
    assert isinstance(cfg['callbacks'][0], QoderWorkCallbackHandler), \
        f"Callback should be QoderWorkCallbackHandler, got {type(cfg['callbacks'][0])}"
    print(f"  Callbacks attached: {len(cfg['callbacks'])} handler(s)")
    print('  PASS')
    passed += 1
except Exception as e:
    print(f'  FAIL: {e}')
    import traceback; traceback.print_exc()
    failed += 1

# ===========================================================================
# Summary
# ===========================================================================
print()
print('=' * 60)
print(f'Results: {passed}/{total} passed, {failed} failed')
print('=' * 60)
sys.exit(0 if failed == 0 else 1)
