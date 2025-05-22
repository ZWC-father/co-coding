from __future__ import annotations
import json, time
from pathlib import Path
from typing import List, Dict, Optional, Callable
import httpx, openai                 # pip install openai>=1.12  :contentReference[oaicite:0]{index=0}
from openai import OpenAIError
"""
OpenAISession —— 兼容 SiliconFlowSession 接口的官方 SDK 版本
-------------------------------------------------------------
"""

class GenerationInterrupted(Exception):
    """手动中断生成时抛出"""
    pass

class OpenAISession:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
        enable_thinking: bool = False,
        thinking_budget: int = 16384,
        timeout: int = 60,
        max_tokens: int = 4096,
        extra_params: Optional[Dict] = None,
    ):
        # 禁用系统代理
        httpx_client = httpx.Client(trust_env=False, timeout=timeout)
        self.client = openai.OpenAI(
            api_key=api_key,
            http_client=httpx_client,
            base_url="https://api.deepseek.com/",
            timeout=timeout
        )
        self.model = model
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.extra = extra_params or {}

        self.history: List[Dict[str, str]] = []
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

        Path("debug_payloads").mkdir(exist_ok=True)
        # 中断标志
        self._stop = False

    def stop(self):
        """
        手动中断当前 send 生成过程。
        """
        self._stop = True

    def send(
        self,
        user_input: str,
        *,
        on_resp: Optional[Callable[[str], None]] = None,
        on_think: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        stream: bool = True,
    ) -> Dict[str, int]:
        """流式模式：回答→on_resp，思考链→on_think；两者均推给 on_chunk"""
        # 重置中断标志
        self._stop = False

        # 累积上下文
        self.history.append({"role": "user", "content": user_input})
        history_copy = json.loads(json.dumps(self.history, ensure_ascii=False))

        # 构建请求
        request_kwargs = {
            "model": self.model,
            "messages": history_copy,
            "stream": stream,
            "max_tokens": self.max_tokens,
            "stream_options": {"include_usage": True},
            **self.extra,
        }
        if self.enable_thinking:
            request_kwargs["enable_thinking"] = True
            request_kwargs["thinking_budget"] = self.thinking_budget

        # 写调试 payload
        payload_file = f"debug_payloads/payload_{self.model}_{int(time.time()*1000)}.json"
        try:
            Path(payload_file).write_text(
                json.dumps(request_kwargs, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[WARN] 无法写调试文件: {e}")

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        answer_parts: List[str] = []

        try:
            # 发起流式请求
            stream_iter = self.client.chat.completions.create(**request_kwargs)
            for chunk in stream_iter:
                # 检查中断
                if self._stop:
                    raise GenerationInterrupted("已手动中断生成")

                if not chunk.choices:
                    raise ValueError("API 返回缺失 `choices` 字段")
                delta = chunk.choices[0].delta

                # 处理思考链
                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    if on_think: on_think(rc)
                    if on_chunk: on_chunk(rc)

                # 处理回答
                cc = getattr(delta, "content", None)
                if cc:
                    if on_resp: on_resp(cc)
                    if on_chunk: on_chunk(cc)
                    answer_parts.append(cc)

                fr = getattr(chunk.choices[0], "finish_reason", None)
                # 当 finish_reason 明确非 "stop" 且不为空，视为异常终止
                if fr and fr != "stop":
                    raise RuntimeError(f"生成被意外中断，finish_reason={fr}")

                # 最后一个 chunk 带 usage
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }

        except GenerationInterrupted:
            # 中断不自毁，但清空标志，历史保留中断前状态
            self._stop = False
            raise
        except OpenAIError as e:
            self._self_destruct()
            raise RuntimeError(f"OpenAI API 错误: {e}") from e
        except Exception:
            # 其它异常自毁并抛出
            self._self_destruct()
            raise

        # 拼接并保存历史
        final_answer = "".join(answer_parts)
        self.history.append({"role": "assistant", "content": final_answer})
        print(f"\nToken Usage: {usage}")
        return usage

    def _self_destruct(self):
        """删除自身以防重复使用"""
        try:
            del self.history
            del self.client
            del self
        except:
            pass

