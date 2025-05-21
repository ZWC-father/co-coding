import requests
import json
import io
import math
from typing import Callable, Dict, List, Optional

class SiliconFlowSession:
    """
    支持上下文管理、流式输出、自动截断以及异常抛出的 SiliconFlow 会话类。

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
        self.endpoint = f"{base_url.rstrip('/')}" + "/chat/completions"
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
            {"role": "system", "content": "写代码一律用C++."}
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

        def total_tokens(msgs):
            return sum(self._estimate_tokens(m["content"]) for m in msgs)

        system_msg = self.history[:1]
        other_msgs = self.history[1:]

        while other_msgs and total_tokens(system_msg + other_msgs) > self.max_history_tokens:
            other_msgs.pop(0)

        self.history = system_msg + other_msgs

    def send(self,
             user_input: str,
             on_chunk: Callable[[str], None],
             use_wrapper: bool = False
    ) -> Dict[str, int]:
        """
        发送用户消息，流式接收并回调增量内容。
        出现任何异常时会抛出，成功返回 usage 统计信息。

        参数:
            user_input: 新的用户输入文本
            on_chunk:    增量文本回调，收到内容后立即调用
            use_wrapper: 是否使用 TextIOWrapper 逐行解码

        返回:
            usage: 包含 prompt_tokens, completion_tokens, total_tokens 的字典
        """
        # 追加用户输入并截断历史
        self.history.append({"role": "user", "content": user_input})
        self._truncate_history()

        payload = {
            "model": self.model,
            "messages": self.history,
            "stream": True,
            "max_tokens": self.max_tokens,
            **self.extra
        }

        # 发起请求
        try:
            resp = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
                stream=True
            )
        except requests.RequestException as e:
            raise RuntimeError(f"请求失败: {e}")

        # 非 200 抛出异常并输出原始错误信息
        if resp.status_code != 200:
            raw = resp.text or resp.content
            raise RuntimeError(f"HTTP {resp.status_code}: {raw}")

        # 强制使用 UTF-8 解码
        resp.encoding = 'utf-8'

        usage_stats: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # 解析流式响应
        if use_wrapper:
            wrapper = io.TextIOWrapper(resp.raw, encoding='utf-8', errors='ignore', newline='')
            for line in wrapper:
                if not line:
                    continue
                if line.startswith('data:'):
                    data_str = line[len('data:'):].strip()
                    if data_str == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    # 更新 usage
                    if 'usage' in chunk:
                        usage_stats = chunk['usage']
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content") or delta.get("reasoning_content")
                        if text:
                            on_chunk(text)
        else:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                # 只处理 data: 前缀行
                if not raw_line.startswith("data:"):
                    continue
                data_str = raw_line.removeprefix("data:").strip()
                # 检查结束标志
                if data_str == '[DONE]':
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                # 更新 usage
                if 'usage' in chunk:
                    usage_stats = chunk['usage']
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    text = delta.get("content") or delta.get("reasoning_content")
                    if text:
                        on_chunk(text)

        # 打印并返回 usage 统计信息
        print(f"\n[Usage] prompt_tokens={usage_stats['prompt_tokens']}, "
              f"completion_tokens={usage_stats['completion_tokens']}, "
              f"total_tokens={usage_stats['total_tokens']}")
        return usage_stats


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
        extra_params={"temperature": 0.7, "top_p": 0.9, "enable_thinking": False}
    )

    # 第一次对话
    parts = []
    session.send(
        user_input="实现一段代码，连续把电脑重启十次",
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

