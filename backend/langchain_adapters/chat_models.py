# langchain_adapters/chat_models.py — ChatQoderWork
#
# 把项目现有的 LLMManager (单例 + 7 task slot) 包装为 LangChain BaseChatModel，
# 让 LCEL / Agent / Retriever 链能无缝调用。适配器只做转发，不复制
# 模型加载 / 量化 / VRAM 管理 / 流式桥接 等底层逻辑。

from __future__ import annotations

import asyncio
import queue as _queue
import threading
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
)
from langchain_core.outputs import (
    ChatGeneration,
    ChatGenerationChunk,
    ChatResult,
)
from pydantic import Field


# ---------------------------------------------------------------------------
# 工具：把 LangChain BaseMessage 列表转成 LLMManager 接受的 OpenAI dict 格式
# ---------------------------------------------------------------------------
def _messages_to_dicts(messages: List[BaseMessage]) -> List[Dict[str, str]]:
    """BaseMessage → {"role": "...", "content": "..."} 列表。

    优先用 langchain-core 提供的官方转换；如不可用则按类型回退手写。
    """
    try:
        from langchain_core.messages import convert_to_openai_messages  # type: ignore

        converted = convert_to_openai_messages(messages)
        # convert_to_openai_messages 可能返回单个 dict（单消息），统一成 list
        if isinstance(converted, dict):
            converted = [converted]
        return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in converted]
    except Exception:
        out: List[Dict[str, str]] = []
        for m in messages:
            role = "user"
            t = getattr(m, "type", "") or ""
            if t == "system":
                role = "system"
            elif t in ("ai", "assistant"):
                role = "assistant"
            elif t in ("human", "user"):
                role = "user"
            elif t == "tool":
                role = "tool"
            content = m.content if isinstance(m.content, str) else str(m.content or "")
            out.append({"role": role, "content": content})
        return out


# ---------------------------------------------------------------------------
# 主适配器
# ---------------------------------------------------------------------------
class ChatQoderWork(BaseChatModel):
    """BaseChatModel 适配器：转发到项目内部 LLMManager 单例。

    用法:
        chat = ChatQoderWork(task="translate")
        ai_msg = chat.invoke([("system", "你是翻译官"), ("user", "Hello")])
        for chunk in chat.stream([("user", "Hello")]):
            print(chunk.content, end="", flush=True)

    注意：
    - `task` 是本项目 7 slot 之一：paragraph_translate / epub_replace / kb_build
      / long_text_translate / translate / default / epub
    - 真正的模型加载、流式、VRAM 管理全在 LLMManager + Provider 内部完成；
      本适配器只负责接口适配。
    - 异步方法 (_agenerate / _astream) 通过 asyncio.to_thread 转发同步方法，
      不会阻塞事件循环。
    """

    task: str = Field(default="default", description="LLMManager task slot")
    model_name: str = Field(default="qoderwork", description="模型名（用于 repr / 日志）")
    streaming: bool = Field(default=True, description="默认是否流式")

    class Config:
        arbitrary_types_allowed = True

    # ------------------------------------------------------------------
    # 必需的元信息
    # ------------------------------------------------------------------
    @property
    def _llm_type(self) -> str:
        return "qoderwork-chat"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"task": self.task, "model_name": self.model_name}

    # ------------------------------------------------------------------
    # 同步核心
    # ------------------------------------------------------------------
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        from model_providers import LLMManager  # lazy import，避免模块加载时副作用

        manager = LLMManager()
        payload = _messages_to_dicts(messages)

        gen_kwargs: Dict[str, Any] = dict(kwargs)
        if stop:
            gen_kwargs["stop"] = stop

        text = manager.chat(payload, task=self.task, **gen_kwargs)

        msg = AIMessage(content=text)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        from model_providers import LLMManager

        manager = LLMManager()
        payload = _messages_to_dicts(messages)

        gen_kwargs: Dict[str, Any] = dict(kwargs)
        if stop:
            gen_kwargs["stop"] = stop

        for chunk in manager.chat_stream(payload, task=self.task, **gen_kwargs):
            if not chunk:
                continue
            cg = ChatGenerationChunk(message=AIMessageChunk(content=chunk))
            if run_manager:
                run_manager.on_llm_new_token(chunk, chunk=cg)
            yield cg

    # ------------------------------------------------------------------
    # 异步版本
    # ------------------------------------------------------------------
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步非流式：把 _generate 推到线程池，不阻塞事件循环。"""
        return await asyncio.to_thread(
            self._generate, messages, stop=stop, run_manager=run_manager, **kwargs
        )

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """异步流式：queue 桥接模式，保证逐 token yield。

        基类默认的 _astream 会把 _stream 整体跑在 executor 里再一次性返回，
        导致 chain.astream() 只产出 1 个 chunk。这里用 daemon 线程 + Queue
        桥接同步 _stream，让每个 token 到达时立即 yield 给上层 LCEL 链。
        """
        q: _queue.Queue = _queue.Queue()

        def _worker():
            try:
                for chunk in self._stream(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                ):
                    q.put(chunk)
            except Exception as e:
                q.put(("__error__", e))
            finally:
                q.put(None)  # sentinel

        t = threading.Thread(target=_worker, daemon=True, name="chat-astream")
        t.start()

        while True:
            item = await asyncio.to_thread(q.get)
            if item is None:
                break
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "__error__":
                raise item[1]
            yield item  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Token 估算
    # ------------------------------------------------------------------
    def get_num_tokens(self, text: str) -> int:
        """粗略估算 token 数：中文≈1.5字符/token，英文≈4字符/token。"""
        if not text:
            return 0
        # 尝试用底层 tokenizer（若有）
        try:
            from model_providers import LLMManager

            provider = LLMManager().get_provider(self.task)
            tok = getattr(provider, "_tokenizer", None)
            if tok is not None:
                return int(len(tok.encode(text)))
        except Exception:
            pass
        # 回退：粗算
        cn = sum(1 for c in text if "一" <= c <= "鿿")
        return max(1, int(cn / 1.5 + (len(text) - cn) / 4))
