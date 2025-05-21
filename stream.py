import requests
import json
import io
from typing import Callable, Dict, List, Optional

class SiliconFlowStreamer:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.siliconflow.cn/v1",
        timeout: int = 30,
        max_tokens: int = 512,
        extra_params: Optional[Dict] = None
    ):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.extra = extra_params or {}

    def send_message(
        self,
        messages: List[Dict[str, str]],
        on_chunk: Callable[[str], None],
        use_wrapper: bool = False,
        stop_on_error: bool = False
    ):
        payload = {
            "model": self.model,
            "messages": messages,
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
            resp.raise_for_status()
            # 强制使用 UTF-8 编码
            resp.encoding = 'utf-8'
        except requests.RequestException as e:
            if stop_on_error: raise
            print(f"[ERROR] 请求失败: {e}")
            return

        try:
            if use_wrapper:
                # 使用 TextIOWrapper 明确解码
                wrapper = io.TextIOWrapper(resp.raw, encoding='utf-8', errors='ignore', newline='')
                for line in wrapper:
                    if not line or line.strip() == '[DONE]': break
                    if not line.startswith('data:'): continue
                    chunk = json.loads(line[len('data:'):].strip())
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content") or delta.get("reasoning_content")
                        if text: on_chunk(text)
            else:
                # 使用 iter_lines 手动过滤并解码
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line or raw_line.strip() == "[DONE]": continue
                    if not raw_line.startswith("data:"): continue
                    try:
                        chunk = json.loads(raw_line.removeprefix("data:").strip())
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content") or delta.get("reasoning_content")
                        if text: on_chunk(text)
        except Exception as e:
            if stop_on_error: raise
            print(f"[ERROR] 流式处理异常: {e}")


def print_callback(text: str):
    """简单的回调函数，把收到的增量直接打印到屏幕。"""
    print(text, end="", flush=True)

if __name__ == "__main__":
    # 1. 填写你的 API Key
    API_KEY = "sk-mhbcxdzidixwkpmyjhrnfediefgalzjpxlmxnamqzurfbikk"

    # 2. 创建 Streamer 实例，并可在 extra_params 中自定义参数
    streamer = SiliconFlowStreamer(
        api_key=API_KEY,
        model="Qwen/Qwen3-8B",
        timeout=30,
        max_tokens=1024,
        extra_params={
            "temperature": 0.7,
            "top_p": 0.7,
            "frequency_penalty": 0.5,
            "enable_thinking": False,
            "thinking_budget": 4096
        }
    )

    # 3. 构造对话上下文
    messages = [
        {"role": "user",      "content": "我刚才问的你什么，你再检查一下代码是否正确"}
    ]

    print("=== 生成开始 ===")
    # 4. 发送消息并启动流式输出
    streamer.send_message(messages, on_chunk=print_callback)
    print("\n=== 生成结束 ===")

