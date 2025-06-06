from __future__ import annotations
import json, time
from pathlib import Path
from typing import List, Dict, Optional, Callable
import httpx, openai                 #openai >= 1.12
from openai import OpenAIError

class GenerationInterrupted(Exception):
    """手动中断生成时抛出"""
    pass

class OpenAISession:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        model: str = "gpt-4o",
        timeout: int = 60,
        max_tokens: int = 8192,
        system_as_user: bool = True,
        trust_env: bool = False,
        extra_params: Optional[Dict] = None,
    ):
        # 禁用系统代理
        httpx_client = httpx.Client(trust_env=trust_env, timeout=timeout)
        self.client = openai.OpenAI(
            http_client=httpx_client,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout
        )
        self.model = model
        self.max_tokens = max_tokens
        self.system_as_user = system_as_user
        self.extra = extra_params or {}
        self.history: List[Dict[str, str]] = []
        self._stop = False

        Path("debug_payloads").mkdir(exist_ok=True)

    def set_sys_prompt(self, prompt):
        if not self.history:
            if self.system_as_user:
                self.history.append({"role": "user", "content": prompt})
            else:
                self.history.append({"role": "system", "content": prompt})

        else:
            raise ValueError("设置系统提示词失败：历史不为空")
    
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
    ) -> Dict[str, int]:
        """流式模式：回答→on_resp，思考链→on_think；两者均推给 on_chunk"""
        # 重置中断标志
        if self._stop:
            self._self_destruct()
            raise GenerationInterrupted("已手动终止生成")

        # 累积上下文
        self.history.append({"role": "user", "content": user_input})
        history_copy = json.loads(json.dumps(self.history, ensure_ascii=False))

        # 构建请求
        request_kwargs = {
            "model": self.model,
            "messages": history_copy,
            "stream": True,
            "max_tokens": self.max_tokens,
            "stream_options": {"include_usage": True},
            **self.extra,
        }

        # 写调试 payload
        payload_file = f"debug_payloads/payload_{int(time.time()*1000)}.json"
        try:
            p = Path(payload_file)
            if not p.parent.exists(): p.parent.mkdir(parents=True)
            p.write_text(
                json.dumps(request_kwargs, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"无法写调试文件: {e}")

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
                    continue

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
                if fr and fr != "stop":
                    raise RuntimeError(f"生成被意外中断，finish_reason={fr}")

                # 最后一个 chunk 带 usage
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }

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
        #print(f"\nToken Usage: {usage}")
        return usage

    def _self_destruct(self):
        """删除自身以防重复使用"""
        try:
            del self.history
            del self.client
            del self
        except:
            pass

