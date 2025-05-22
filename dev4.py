import os, sys, json, subprocess, pathlib, re, time
import shutil
import textwrap
from pathlib import Path
from typing import List, Dict, Optional, Callable
import requests


# ─────────────────────────────────────────────────────────────
# SiliconFlowSession（去除固定 C++ 默认提示，改为可选 system_prompt）
# ─────────────────────────────────────────────────────────────
class SiliconFlowSession:
    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: Optional[str] = None,
        enable_thinking: bool = True,
        thinking_budget: int = 1024,
        timeout: int = 30,
        max_tokens: int = 8192,
        extra_params: Optional[Dict] = None,
    ):
        self.endpoint = "https://api.siliconflow.cn/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        self.model, self.timeout, self.max_tokens = model, timeout, max_tokens
        self.enable_thinking, self.thinking_budget = enable_thinking, thinking_budget
        self.extra = extra_params or {}
        self.history: List[Dict[str, str]] = []
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})
        Path("debug_payloads").mkdir(exist_ok=True)

    # ---------------- send ----------------
    def send(
        self,
        user_input: str,
        *,
        on_resp: Optional[Callable[[str], None]] = None,
        on_think: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        stream: bool = True,
    ) -> Dict[str, int]:
        """仅支持 stream=True。思考→on_think；回答→on_resp；二者都推给 on_chunk"""
        # 追加用户消息
        self.history.append({"role": "user", "content": user_input})

        # 深拷贝 history，避免后续变动造成调试 / 发送不一致
        history_copy = json.loads(json.dumps(self.history, ensure_ascii=False))

        payload = {
            "model": self.model,
            "messages": history_copy,
            "stream": stream,
            "max_tokens": self.max_tokens,
            "enable_thinking": self.enable_thinking,
            "thinking_budget": self.thinking_budget,
            **self.extra,
        }

        # 写调试 JSON
        fname = f"debug_payloads/payload_{self.model.replace('/','_')}_{int(time.time()*1000)}.json"
        try:
            Path(fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] 调试文件写入失败: {e}")

        # 发送请求
        resp = requests.post(self.endpoint, headers=self.headers, json=payload,
                             timeout=self.timeout, stream=True)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        resp.encoding = "utf-8"

        usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        answer_parts: List[str] = []

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
                rc = delta.get("reasoning_content")
                cc = delta.get("content")

                if rc:
                    if on_think:
                        on_think(rc)
                    if on_chunk:
                        on_chunk(rc)
                if cc:
                    if on_resp:
                        on_resp(cc)
                    if on_chunk:
                        on_chunk(cc)
                    answer_parts.append(cc)

        # 记录 assistant 完整回复
        final_answer = "".join(answer_parts)
        self.history.append({"role": "assistant", "content": final_answer})
#       usage["answer"] = final_answer  # 便于调试返回
        return usage

# ───────────────────────────────
# 工具函数
# ───────────────────────────────
#CODE_RE = re.compile(r"```(?:python)?\s*([\s\S]+?)```", re.IGNORECASE)
#def extract_code(text: str) -> str:
#    m = CODE_RE.search(text)
#    return (m.group(1) if m else text).strip()
FENCE_RE = re.compile(r"```(?:python)?\n([\s\S]+?)\n```", re.IGNORECASE)

def extract_code(text: str) -> str:
    # 1. 提取代码块或整段
    m = FENCE_RE.search(text)
    code = m.group(1) if m else text

    # 2. 去掉公共缩进
    dedented = textwrap.dedent(code)

    # 3. 按行分割，剔除首尾空行
    lines: List[str] = dedented.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)

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

    del_path = Path("debug_payloads")
    shutil.rmtree(del_path)

    model_analyst = "Qwen/Qwen3-14B"
    model_developer = "Qwen/Qwen3-32B"
    model_tester = "deepseek-ai/DeepSeek-V3"

    analyst = SiliconFlowSession(
        api_key=token,
        model=model_analyst,
        system_prompt=(
            "你接下来扮演开发需求分析，根据用户的初始输入，生成便于开发者理解"
            "的具体需求，注意开发者使用python编程，且只能从stdin读取信息，"
            "从stdout打印运行结果，不能实现图形化。而且测试工程师使用黑盒测试，通过脚本检查开发者代码的输出，"
            "为了方便测试，你不要给他们过高的要求，只要包含关键点即可，不要写代码"
        ),
    )

    developer = SiliconFlowSession(
        api_key=token,
        model=model_developer,
        system_prompt=(
            "你扮演开发者，根据需求分析师的分析，完成一个python项目（我们会把你的代码保存为solution.py），"
            "不要包含危险的系统调用，输出只含一段代码，程序的输入全部来自stdin，运行结果输出到stdout。"
            "写必要的注释，可以输出格式化的调试信息，便于自动化测试。"
            "测试工程师（也是AI）会写一个黑盒测试脚本以测评你的代码（所以你要严格规范输出格式），"
            "如果他给你指出错误，你需要修改代码重新输出。"
        ),
    )

    tester = SiliconFlowSession(
        api_key=token,
        model=model_tester,
        system_prompt=(
            "你扮演测试工程师，根据需求分析师的描述和开发者提供的代码，生成python测试脚本，"
            "脚本包含多个测试用例和期望输出，"
            "和调用开发者代码（可以直接用python3 solution.py调用，他的代码会从stdin输入，从stdout输出）的模块，"
            "就像online judge的自动化测试一样（可以输出测试信息，便于排查问题）"
            "如果测试全部通过，返回0，否则返回1。"
            "你要仔细阅读开发者的代码，注意代码的输出会有不确定性，所以不要过于严格地匹配输出，要增强测试的鲁棒性。"
            "你只需要提供一个python代码块作为测试脚本。我会帮你保存为test_solution.py并运行。"
            "注意：如果测试失败，我会把运行结果给你，提示你生成错误报告（分析原因，提供重要信息，但不要帮开发者修改）。"
            "警告：如果发现是你的测试脚本（test_solution.py）写错了，而非开发者的代码（solution.py）本身有错，"
            "你就输出:\"[[TEST_ERROR]]\"，然后什么都不要说！我随后会提示你重新生成完整的测试脚本。"
            "如果测评再次失败，我会给你指令，让你再次生成错误报告，或重新生成测试脚本。"
        ),
    )

    def developing(developer, prompt) -> str:
        print("\n\n=== 开发者输出 ===")
        print("\nTokens使用情况:", developer.send(prompt,
                                 on_resp=printer(GREEN), on_think=printer(YELLOW)))
        dev_code = extract_code(developer.history[-1]["content"])
        print("\n\n--- 开发者代码 (solution.py) ---")
        print(dev_code)
        input("\n确认后按回车继续…")
        save("solution.py", dev_code)
        return dev_code

    def test_developing(tester, prompt):
        print("\n=== 测试工程师输出 ===")
        print("\nTokens使用情况:", tester.send(prompt,
                                 on_resp=printer(GREEN), on_think=printer(YELLOW)))
        test_code = extract_code(tester.history[-1]["content"])
        print("\n\n--- 测试脚本 (test_solution.py) ---")
        print(test_code)
        input("\n确认后按回车继续…")
        save("test_solution.py", test_code)

    def test_reporting(tester, prompt) -> str:
        print("\n=== 测试工程师输出 ===")
        print("\nTokens使用情况:", tester.send(prompt,
                                 on_resp=printer(GREEN), on_think=printer(YELLOW)))
        report = tester.history[-1]["content"]
        print("\n--- 错误报告 ---")
        print(report)
        return report

    
    print("=== 需求分析师输出 ===")
    analyst.send(raw_req, on_resp=printer(GREEN), on_think=printer(YELLOW))
    analysis = analyst.history[-1]["content"]

    # --- 2. 开发 ---
    dev_code = developing(developer, f"开发需求如下：\n{analysis}")

    # --- 3. 生成测试脚本 ---
    test_developing(tester, f"需求描述：\n{analysis}\n\n\n开发者代码：\n{dev_code}")


    # --- 4. 测试循环 ---
    for rnd in range(1, 5):
        print(f"\n=== Round {rnd} 运行测试 ===")
        res = subprocess.run([sys.executable, "test_solution.py"],
                             capture_output=True, text=True, timeout=60)
        print("---- stdout ----")
        print(res.stdout or "<空>")
        print("---- stderr ----")
        print(res.stderr or "<空>")

        if res.returncode == 0:
            print("🎉 测试全部通过，开发完成！"); break

        # 让测试工程师生成错误报告
        report = test_reporting(tester, f"以下是测试输出：\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"),

        if "[[TEST_ERROR]]" in report:
            # 测试脚本本身有误
            print("⚠️  测试脚本有误，重新生成…")
            test_developing(tester, f"重新生成完整的测试脚本。")
            continue

        # 开发者修复代码
        print("❌ 代码需修复…")
        developing(developer, f"错误报告：\n{report}")

    else:
        print("⛔ 达到最大迭代次数，仍未通过测试。")

if __name__ == "__main__":
    main()
