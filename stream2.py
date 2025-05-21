import requests
import json
import io
import math
from typing import Callable, Dict, List, Optional

class SiliconFlowSession:
    """
    支持上下文管理、流式输出和自动截断的 SiliconFlow 会话类。

    参数:
        api_key:            SiliconFlow 的 Bearer Token
        model:              模型名称
        base_url:           API 基础 URL，默认 https://api.siliconflow.cn/v1
        timeout:            HTTP 请求超时时间（秒）
        max_tokens:         生成内容的最大 token 数
        max_history_tokens: 历史上下文的最大 token 数，超过时自动截断最早消息
        extra_params:       额外的请求参数，比如 temperature, top_p 等
    """
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.siliconflow.cn/v1",
        timeout: int = 30,
        max_tokens: int = 512,
        max_history_tokens: Optional[int] = None,
        extra_params: Optional[Dict] = None
    ):
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_history_tokens = max_history_tokens
        self.extra = extra_params or {}
        # 初始化对话历史，system 消息放首位
        self.history: List[Dict[str, str]] = [
            {"role": "system", "content": "You are a helpful assistant."}
        ]

    def _estimate_tokens(self, text: str) -> int:
        """
        简单估算 Token 数量：按每 4 字符计 1 token
        """
        return math.ceil(len(text) / 4)

    def _truncate_history(self):
        """
        如果总历史 token 数超过 max_history_tokens，
        则依次丢弃最早的非 system 消息，直到满足限制。
        """
        if self.max_history_tokens is None:
            return

        # 计算当前历史总 token 数
        def total_tokens(msgs):
            return sum(self._estimate_tokens(m["content"]) for m in msgs)

        # 保留 system 消息，不动
        system_msg = self.history[0:1]
        other_msgs = self.history[1:]

        # 截断最早消息
        while other_msgs and total_tokens(system_msg + other_msgs) > self.max_history_tokens:
            other_msgs.pop(0)

        self.history = system_msg + other_msgs

    def send(
        self,
        user_input: str,
        on_chunk: Callable[[str], None],
        stop_on_error: bool = False,
        use_wrapper: bool = False
    ):
        """
        发送用户消息，流式接收并回调增量内容。

        Parameters:
            user_input:   用户输入文本
            on_chunk:     每接收到一小段输出时的回调函数，传入字符串
            stop_on_error:遇到错误时是否抛出异常
            use_wrapper:  是否使用 TextIOWrapper 逐行解码
        """
        # 追加用户输入
        self.history.append({"role": "user", "content": user_input})
        # 根据 max_history_tokens 自动截断
        self._truncate_history()

        payload = {
            "model": self.model,
            "messages": self.history,
            "stream": True,
            "max_tokens": self.max_tokens,
            **self.extra
        }

        try:
            resp = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
                stream=True
            )
        except requests.RequestException as e:
            if stop_on_error:
                raise
            print(f"[ERROR] 请求失败: {e}")
            return

        # 统一处理非 200 响应
        if resp.status_code != 200:
            raw = resp.text or resp.content
            print(f"[ERROR] HTTP {resp.status_code}: {raw}")
            return

        # 强制使用 UTF-8 解码
        resp.encoding = 'utf-8'

        # 解析流式响应
        try:
            if use_wrapper:
                wrapper = io.TextIOWrapper(resp.raw, encoding='utf-8', errors='ignore', newline='')
                for line in wrapper:
                    if not line or line.strip() == '[DONE]':
                        break
                    if not line.startswith('data:'):
                        continue
                    data_str = line[len('data:'):].strip()
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content") or delta.get("reasoning_content")
                        if text:
                            on_chunk(text)
                            # 可选：追加 assistant 回复到 history
                            # self.history.append({"role": "assistant", "content": text})
            else:
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    if raw_line.strip() == "[DONE]":
                        break
                    if not raw_line.startswith("data:"):
                        continue
                    data_str = raw_line[len("data:"):].strip()
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content") or delta.get("reasoning_content")
                        if text:
                            on_chunk(text)
                            # 可选：追加 assistant 回复到 history
                            # self.history.append({"role": "assistant", "content": text})
        except Exception as e:
            if stop_on_error:
                raise
            print(f"[ERROR] 流式处理异常: {e}")


def print_and_collect(text: str, collector: List[str]):
    print(text, end="", flush=True)
    collector.append(text)

if __name__ == "__main__":
    API_KEY = "sk-mhbcxdzidixwkpmyjhrnfediefgalzjpxlmxnamqzurfbikk"

    session = SiliconFlowSession(
        api_key=API_KEY,
        model="deepseek-ai/DeepSeek-R1",
        timeout=20,
        max_tokens=1024,
        max_history_tokens=2048,       # 限制上下文最多约 2000 tokens
        extra_params={"temperature": 0.7, "top_p": 0.9}
    )

    # 第一次对话
    parts = []
    session.send(
        user_input="实现一段代码（python），连续把电脑重启十次",
        on_chunk=lambda t: print_and_collect(t, parts)
    )
    full_reply = "".join(parts)
    session.history.append({"role": "assistant", "content": full_reply})

    # 第二次对话（保持上下文并自动截断）
    parts.clear()
    session.send(
        user_input="我刚才问的你什么问题，你确定你的代码正确？",
        on_chunk=lambda t: print_and_collect(t, parts)
    )
    print("\n对话结束。")

