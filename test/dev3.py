import os, sys, json, io, math, subprocess, pathlib, re, time
from pathlib import Path
from typing import List, Dict, Optional, Callable
import requests


# ─────────────────────────────────────────────────────────────
# SiliconFlowSession（去除固定 C++ 默认提示，改为可选 system_prompt）
# ─────────────────────────────────────────────────────────────
class SiliconFlowSession:
    """
    简化版 SiliconFlowSession：支持流式输出、enable_thinking 选项，以及异常抛出。

    参数:
        api_key:            SiliconFlow 的 Bearer Token
        model:              模型名称
        system_prompt:      可选，作为 system 角色的提示词
        enable_thinking:    是否开启推理链输出
        thinking_budget:    推理预算, 配合 enable_thinking 使用
        timeout:            HTTP 请求超时时间（秒）
        max_tokens:         生成内容的最大 token 数
        extra_params:       额外的请求参数，如 temperature, top_p, stop, min_p, top_k, frequency_penalty, n, response_format, tools

    每次 send 调用前会将完整 payload 写入调试文件，
    文件名形如 'payload_<model>_<timestamp>.json'，避免并发冲突。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: Optional[str] = None,
        enable_thinking: bool = True,
        thinking_budget: int = 512,
        timeout: int = 30,
        max_tokens: int = 8192,
        extra_params: Optional[Dict] = None
    ):
        self.endpoint = "https://api.siliconflow.cn/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.extra = extra_params or {}
        # 初始化对话历史，仅包含 system_prompt
        self.history: List[Dict[str, str]] = []
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})
        # 确保 debug 目录存在
        Path("debug_payloads").mkdir(exist_ok=True)

    def send(
        self,
        user_input: str,
        on_resp: Optional[Callable[[str], None]] = None,
        on_think: Optional[Callable[[str], None]] = None,
        # 旧版 on_chunk 继续兼容：若给了就两者同用
        on_chunk: Optional[Callable[[str], None]] = None,
        stream: bool = True
    ) -> Dict[str, int]:
        """仅流式模式。on_resp→content，on_think→reasoning_content"""
        self.history.append({"role": "user", "content": user_input})

        payload = {
            "model": self.model,
            "messages": self.history,
            "stream": stream,
            "max_tokens": self.max_tokens,
            "enable_thinking": self.enable_thinking,
            "thinking_budget": self.thinking_budget,
            **self.extra,
        }

        # --- 写调试文件（保持不变） ---
        fname = f"debug_payloads/payload_{self.model.replace('/','_')}_{int(time.time()*1000)}.json"
        try:
            Path(fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] payload 写入失败: {e}")

        # --- 请求 ---
        resp = requests.post(self.endpoint, headers=self.headers, json=payload,
                             timeout=self.timeout, stream=True)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        resp.encoding = "utf-8"

        usage = {"prompt_tokens":0, "completion_tokens":0, "total_tokens":0}
        full_reply: List[str] = []

        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            if "usage" in chunk:
                usage = chunk["usage"]

            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                # 思考内容
                rc = delta.get("reasoning_content")
                if rc:
                    if on_think:
                        on_think(rc)
                    if on_chunk:
                        on_chunk(rc)
                # 最终回答
                cc = delta.get("content")
                if cc:
                    full_reply.append(cc)
                    if on_resp:
                        on_resp(cc)
                    if on_chunk:
                        on_chunk(cc)

        self.history.append({"role": "assistant", "content": "".join(full_reply)})
        return usage


# ───────────────────────────────
# 工具函数
# ───────────────────────────────
#CODE_RE = re.compile(r"```(?:python)?\s*([\s\S]+?)```", re.IGNORECASE)
#def extract_code(text: str) -> str:
#    m = CODE_RE.search(text)
#    return (m.group(1) if m else text).strip()

# 匹配三重反引号代码块
FENCE_RE = re.compile(r"```(?:python)?\s*([\s\S]+?)```", re.IGNORECASE)

# 匹配典型 Python 代码起始行
START_RE = re.compile(r"^\s*(?:#!/usr/bin/env python3|import\s+\w+|def\s+\w+|class\s+\w+)", re.MULTILINE)

def extract_code(text: str) -> str:
    """
    从模型输出 text 中提取代码：
    1. 如果有三重反引号，取最后一个代码块内容。
    2. 否则，从第一个以 import/def/class/#! 开头的行截取到末尾。
    3. 再不然，就返回整个文本。
    """
    # 1. 尝试所有反引号块，取最后一个
    fences: List[re.Match] = list(FENCE_RE.finditer(text))
    if fences:
        last = fences[-1]
        return last.group(1).strip()

    # 2. 没有代码块，找第一个典型 Python 代码行
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if START_RE.match(line):
            return "\n".join(lines[idx:]).strip()

    # 3. 最后退化：返回原文
    return text.strip()

GREEN = "\x1b[92m"; YELLOW = "\x1b[93m"; RESET = "\x1b[0m"

def printer(color=""):
    def _cb(txt):
        print(f"{color}{txt}{RESET}", end="", flush=True)
    return _cb

def save(path: str, content: str):
    pathlib.Path(path).write_text(content, encoding="utf-8")


# ───────────────────────────────
# 主流程
# ───────────────────────────────
def main():
    token = os.getenv("SILICONFLOW_API_KEY")
    if not token:
        print("SILICONFLOW_API_KEY 未设置")
        sys.exit(1)

    req_file = pathlib.Path("requirement.txt")
    if not req_file.exists():
        print("缺少 requirement.txt")
        sys.exit(1)
    raw_req = req_file.read_text(encoding="utf-8").strip()

    model = "Qwen/Qwen3-32B"

    analyst = SiliconFlowSession(
        api_key=token,
        model=model,
        system_prompt=(
            "你接下来扮演开发需求分析，根据用户的初始输入，生成便于开发者理解"
            "的具体需求，注意开发者使用python编程，且只能从stdin读取信息，"
            "从stdout打印运行结果。不要输出过多信息，只要包含关键点即可，不要写代码"
        ),
    )

    developer = SiliconFlowSession(
        api_key=token,
        model=model,
        system_prompt=(
            "你扮演开发者，根据需求分析师的分析，完成一个python项目（我们会把你的），"
            "不要包含危险的系统调用，输出只含一段代码，程序的输入全部来自stdin，运行结果输出到stdout，"
            "写必要的注释，且可以输出格式化的调试信息，便于自动化测试。"
            "如果测试工程师(也由AI扮演)指出错误，你需要修改代码重新输出。"
        ),
    )

    tester = SiliconFlowSession(
        api_key=token,
        model=model,
        system_prompt=(
            "你扮演测试工程师，根据需求分析师的描述和开发者提供的代码，生成python测试脚本，"
            "脚本包含多个测试用例和期望输出，"
            "和调用开发者代码（可以直接用python3 solution.py调用，他的代码会从stdin输入，从stdout输出）的模块，"
            "就像online judge的自动化测试一样（可以输出测试信息，便于排查问题）"
            "如果输出全部符合要求，返回0，否则返回1。"
            "你要仔细阅读开发者的代码，判断可能的输出，输出匹配不要过于严格，要增强测评的鲁棒性。"
            "然后你的生成内容必须只含一个代码块。我们会帮你保存为test_solution.py并运行"
            "如果测试失败，我会把运行结果给你，由你生成错误报告，便于开发者修改。"
            "如果开发者再次给你提供代码，你就继续按照前面的要求生成测试脚本。"
            "注意：如果发现运行错误是因为你而非开发者，请输出[[TEST_ERROR]]标识，我们会引导你重新生成测试脚本。"
        ),
    )
    
    print("=== 需求分析师输出 ===")
    analyst.send(raw_req, on_resp=printer(GREEN), on_think=printer(YELLOW))
    analysis = analyst.history[-1]["content"]

    # --- 2. 开发 ---
    print("\n\n=== 开发者生成代码 ===")
    developer.send(f"开发需求如下：\n{analysis}",
                   on_resp=printer(GREEN), on_think=printer(YELLOW))
    dev_code = extract_code(developer.history[-1]["content"])
    print("\n\n--- 开发者初始代码 (solution.py) ---\n", dev_code)
    input("\n确认后按回车继续…")
    save("solution.py", dev_code)

    # --- 3. 生成测试脚本 ---
    print("\n=== 测试工程师生成测试脚本 ===")
    tester.send(f"需求描述：{analysis}\n\n开发者代码：\n{dev_code}",
                on_resp=printer(GREEN), on_think=printer(YELLOW))
    test_code = extract_code(tester.history[-1]["content"])
    print("\n\n--- 测试脚本 (test_solution.py) ---\n", test_code)
    input("\n确认后按回车继续…")
    save("test_solution.py", test_code)

    # --- 4. 测试循环 ---
    for rnd in range(1, 4):
        print(f"\n=== Round {rnd} 运行测试 ===")
        res = subprocess.run([sys.executable, "test_solution.py"],
                             capture_output=True, text=True, timeout=60)
        print("---- stdout ----\n", res.stdout or "<空>")
        print("---- stderr ----\n", res.stderr or "<空>")

        if res.returncode == 0:
            print("🎉 测试全部通过！"); break

        # 让测试工程师生成错误报告
        tester.send(f"以下是测试输出：\n{res.stdout}\n{res.stderr}",
                    on_resp=printer(GREEN), on_think=printer(YELLOW), stream=False)
        report = tester.history[-1]["content"]
        print("\n--- 错误报告 ---\n", report)

        if "[[TEST_ERROR]]" in report:
            # 测试脚本本身有误
            print("⚠️  测试脚本有误，重新生成…")
            tester.send(f"请修正测试脚本：\n{report}",
                        on_resp=printer(GREEN), on_think=printer(YELLOW))
            test_code = extract_code(tester.history[-1]["content"])
            save("test_solution.py", test_code)
            print("\n已更新 test_solution.py，重新测试。"); continue

        # 开发者修复代码
        print("❌  代码需修复…")
        developer.send(f"错误报告：\n{report}",
                       on_resp=printer(GREEN), on_think=printer(YELLOW))
        dev_code = extract_code(developer.history[-1]["content"])
        save("solution.py", dev_code)
        print("\n已覆盖 solution.py")

    else:
        print("⛔ 达到最大迭代次数，仍未通过测试。")

if __name__ == "__main__":
    main()
