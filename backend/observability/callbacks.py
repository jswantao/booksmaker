# observability/callbacks.py -- LangChain callback handlers for observability
#
# Routes all LCEL chain events (prompt, tool calls, generation, retrieval) to
# logs/langchain.log via Python's RotatingFileHandler. This gives structured,
# timestamped traceability without requiring external services like LangSmith.
#
# Usage:
#     from observability import get_langchain_callbacks
#     chain.ainvoke(input, config={"callbacks": get_langchain_callbacks()})
#
# Or attach at chain construction time:
#     chain = chain.with_config({"callbacks": get_langchain_callbacks()})

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

# Module-level state
_logger_name = "langchain_events"
_initialized = False
_callbacks: List[BaseCallbackHandler] = []


# ---------------------------------------------------------------------------
# Custom callback handler: routes LangChain events to Python logging
# ---------------------------------------------------------------------------
class QoderWorkCallbackHandler(BaseCallbackHandler):
    """Logs LangChain events (chain/LLM/tool/retriever start/end/error) to
    a structured log file. Each event is one line with timestamp + level.
    """

    def __init__(self, logger_name: str = _logger_name):
        super().__init__()
        self._log = logging.getLogger(logger_name)

    # --- Chain events ---
    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        name = (serialized or {}).get("name", "unknown")
        inp_preview = _truncate(str(inputs), 200)
        self._log.info("CHAIN_START  [%s] run=%s input=%s", name, str(run_id)[:8], inp_preview)

    def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        out_preview = _truncate(str(outputs), 300)
        self._log.info("CHAIN_END    run=%s output=%s", str(run_id)[:8], out_preview)

    def on_chain_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._log.error("CHAIN_ERROR  run=%s error=%s", str(run_id)[:8], error)

    # --- LLM / Chat model events ---
    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        name = (serialized or {}).get("name", "unknown")
        n_msgs = sum(len(m) for m in messages)
        self._log.info("LLM_START    [%s] run=%s msgs=%d", name, str(run_id)[:8], n_msgs)

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        usage = response.llm_output or {}
        token_info = ""
        if "token_usage" in usage:
            tu = usage["token_usage"]
            token_info = f" tokens=prompt:{tu.get('prompt_tokens', '?')}/completion:{tu.get('completion_tokens', '?')}"
        out_text = ""
        if response.generations and response.generations[0]:
            out_text = response.generations[0][0].text if hasattr(response.generations[0][0], 'text') else str(response.generations[0][0])
        out_preview = _truncate(out_text, 200)
        self._log.info("LLM_END      run=%s%s output=%s", str(run_id)[:8], token_info, out_preview)

    def on_llm_new_token(self, token, *, run_id, parent_run_id=None, **kwargs):
        self._log.debug("LLM_TOKEN    run=%s token=%r", str(run_id)[:8], token)

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._log.error("LLM_ERROR    run=%s error=%s", str(run_id)[:8], error)

    # --- Tool events ---
    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        name = (serialized or {}).get("name", "unknown")
        self._log.info("TOOL_START   [%s] run=%s input=%s", name, str(run_id)[:8], _truncate(input_str, 200))

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        self._log.info("TOOL_END     run=%s output=%s", str(run_id)[:8], _truncate(str(output), 300))

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._log.error("TOOL_ERROR   run=%s error=%s", str(run_id)[:8], error)

    # --- Retriever events ---
    def on_retriever_start(self, serialized, query, *, run_id, parent_run_id=None, **kwargs):
        name = (serialized or {}).get("name", "unknown")
        self._log.info("RETR_START   [%s] run=%s query=%s", name, str(run_id)[:8], _truncate(query, 100))

    def on_retriever_end(self, documents, *, run_id, parent_run_id=None, **kwargs):
        self._log.info("RETR_END     run=%s docs=%d", str(run_id)[:8], len(documents))

    def on_retriever_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._log.error("RETR_ERROR   run=%s error=%s", str(run_id)[:8], error)

    # --- Text (misc) ---
    def on_text(self, text, *, run_id, parent_run_id=None, **kwargs):
        self._log.debug("TEXT         run=%s text=%s", str(run_id)[:8], _truncate(text, 200))


# ---------------------------------------------------------------------------
# Setup & accessor
# ---------------------------------------------------------------------------
def setup_langchain_logging(
    log_dir: Optional[str] = None,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    level: int = logging.INFO,
) -> None:
    """Initialize the langchain_events logger with a RotatingFileHandler.

    Args:
        log_dir: Directory for log files. Defaults to <project_root>/logs.
        max_bytes: Max size per log file before rotation (default 5MB).
        backup_count: Number of rotated backups to keep (default 3).
        level: Logging level for the file handler (default INFO).
    """
    global _initialized, _callbacks

    if _initialized:
        return

    if log_dir is None:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(backend_dir, "logs")

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "langchain.log")

    evt_logger = logging.getLogger(_logger_name)
    evt_logger.setLevel(level)
    if not evt_logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        evt_logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(fmt)
        evt_logger.addHandler(ch)

    _callbacks = [QoderWorkCallbackHandler()]
    _initialized = True
    evt_logger.info("LangChain logging initialized -> %s (max %dMB, %d backups)",
                    log_path, max_bytes // (1024 * 1024), backup_count)


def get_langchain_callbacks() -> List[BaseCallbackHandler]:
    """Return the list of LangChain callbacks to attach to chain invocations.

    Lazily calls setup_langchain_logging() on first use.
    """
    if not _initialized:
        setup_langchain_logging()
    return list(_callbacks)


def _truncate(s: str, max_len: int = 200) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"... (+{len(s) - max_len})"
