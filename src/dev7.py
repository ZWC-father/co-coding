from __future__ import annotations
import os, sys, json, subprocess, pathlib, re, time, ast, shutil, textwrap
import importlib.util
from pathlib import Path
from typing import List, Dict, Set, Optional, Callable
import httpx, openai                 # pip install openai>=1.12  :contentReference[oaicite:0]{index=0}
from openai import OpenAIError
"""
OpenAISession —— 兼容 SiliconFlowSession 接口的官方 SDK 版本
-------------------------------------------------------------
• 保留 system_prompt、上下文累积、on_resp/on_think/on_chunk 回调
• 支持流式输出；若模型返回 delta.reasoning_content 则触发 on_think
• 额外参数（temperature、top_p、enable_thinking、thinking_budget…）原样透传
• 使用 openai>=1.12 官方 SDK（sync 调用；async 同理）
"""
class GenerationInterrupted(Exception):
    pass

class OpenAISession:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.siliconflow.cn/v1/",
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
        timeout: int = 60,
        max_tokens: int = 4096,
        extra_params: Optional[Dict] = None,
    ):
        # 禁用系统代理
        httpx_client = httpx.Client(trust_env=False, timeout=timeout)
        self.client = openai.OpenAI(
            http_client=httpx_client,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout
        )
        self.model = model
        self.max_tokens = max_tokens
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
            "stream": True,
            "max_tokens": self.max_tokens,
            "stream_options": {"include_usage": True},
            **self.extra,
        }

        # 写调试 payload
        payload_file = f"debug_payloads/payload_{int(time.time()*1000)}.json"
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
                    print("[WARN] API 返回缺失 choices 字段")
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


class DependencyResolver:
    """
    扫描 Python 源文件中的 import 语句，识别缺失的第三方包，
    并在当前 venv 中通过 pip 安装它们。

    usage:
        resolver = DependencyResolver()
        resolver.install_from_files(["solution.py", "test_solution.py"])
    """

    # 标准库模块集合（可根据具体 Python 版本调整）
    _stdlib: Set[str] = set(sys.builtin_module_names)

    def __init__(self, extra_mapping: Optional[dict] = None):
        """
        :param extra_mapping: 可选的模块名到 pip 包名映射，
                              例如 {"yaml": "pyyaml"}。
        """
        self.mapping = extra_mapping or {}

    def _parse_imports(self, filepath: Path) -> Set[str]:
        """
        从单个文件中解析 import 语句，返回模块名集合。
        """
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
        mods: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module.split(".")[0])
        return mods

    def _is_installed(self, module: str) -> bool:
        """
        判断模块是否已安装。
        """
        return importlib.util.find_spec(module) is not None

    def _install_package(self, package: str) -> None:
        """
        使用 pip 安装单个包；失败则抛出 RuntimeError。
        """
        cmd = [sys.executable, "-m", "pip", "install", package]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"依赖安装失败：{package} (exit {e.returncode})") from e

    def install_from_files(self, filepaths: List[str]) -> None:
        """
        扫描多个文件所需依赖并安装。
        """
        # 收集所有 imports
        required: Set[str] = set()
        for fp in filepaths:
            mods = self._parse_imports(Path(fp))
            required.update(mods)

        # 过滤掉标准库和已安装模块
        to_install: List[str] = []
        for mod in sorted(required):
            if mod in self._stdlib or self._is_installed(mod):
                continue
            pkg = self.mapping.get(mod, mod)
            to_install.append(pkg)

        if not to_install:
            print("🎉 未发现需要安装的新依赖。")
            return

        print("🔍 发现新依赖，开始安装：", to_install)
        for pkg in to_install:
            self._install_package(pkg)
        print("✅ 依赖安装完成！")



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

COMMON_DEP_MAPPING = {
    # HTTP 客户端
    "requests": "requests",
    "urllib3": "urllib3",
    "certifi": "certifi",
    "chardet": "chardet",
    "charset_normalizer": "charset-normalizer",

    # 数据科学 / 科学计算
    "numpy": "numpy",
    "scipy": "scipy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "sklearn": "scikit-learn",
    "statsmodels": "statsmodels",
    "sympy": "sympy",

    # 机器学习 / 深度学习
    "tensorflow": "tensorflow",
    "torch": "torch",
    "torchvision": "torchvision",
    "keras": "keras",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",

    # Web 框架
    "flask": "Flask",
    "django": "Django",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "uvicorn": "uvicorn",
    "gunicorn": "gunicorn",

    # ORM / 数据库
    "sqlalchemy": "SQLAlchemy",
    "alembic": "alembic",
    "pymysql": "PyMySQL",
    "psycopg2": "psycopg2-binary",
    "redis": "redis",
    "aioredis": "aioredis",

    # 模板 & Web 工具
    "jinja2": "Jinja2",
    "itsdangerous": "itsdangerous",
    "werkzeug": "Werkzeug",

    # 爬虫 / HTML 解析
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "scrapy": "Scrapy",

    # 图像处理
    "PIL": "Pillow",

    # 测试
    "pytest": "pytest",
    "unittest": "unittest",       # 标准库，一般无需安装
    "hypothesis": "hypothesis",
    "coverage": "coverage",

    # 命令行工具
    "click": "click",
    "typer": "typer",

    # 异步
    "aiohttp": "aiohttp",
    "httpx": "httpx",
    "asyncio": "asyncio",         # 标准库，无需安装

    # 加密
    "cryptography": "cryptography",
    "Crypto": "pycryptodome",
    "jwt": "PyJWT",

    # 文件 & 数据格式
    "yaml": "PyYAML",
    "jsonschema": "jsonschema",
    "toml": "toml",
    "xmltodict": "xmltodict",

    # 工具库
    "tqdm": "tqdm",
    "python_dotenv": "python-dotenv",
    "lockfile": "lockfile",
    "psutil": "psutil",
    "watchdog": "watchdog",

    # 网络 & WebSocket
    "websocket": "websocket-client",
    "websockets": "websockets",

    # 图论
    "networkx": "networkx",

    # 其他常见
    "dateutil": "python-dateutil",
    "pytz": "pytz",
    "tzlocal": "tzlocal",
    "pathlib": "pathlib",          # 标准库 (3.4+)
    "typing_extensions": "typing-extensions",
}

# ───────────────────────────────
# 主流程
# ───────────────────────────────
def main():
    token = os.getenv("API_KEY")
    if not token:
        print("API_KEY 未设置")
        sys.exit(1)

    req_file = pathlib.Path("requirement.txt")
    if not req_file.exists():
        print("缺少 requirement.txt")
        sys.exit(1)
    raw_req = req_file.read_text(encoding="utf-8").strip()

    del_path = Path("debug_payloads")
    shutil.rmtree(del_path, ignore_errors=True)

    model_analyst = "Qwen/Qwen3-14B"
    model_developer = "Qwen/Qwen3-235B-A22B"
    model_tester = "Qwen/Qwen3-235B-A22B"

#    analyst = SiliconFlowSession(
#        api_key=token,
#        model=model_analyst,
#        system_prompt=(
#            "你接下来扮演开发需求分析，根据用户的初始输入，生成便于开发者理解"
#            "的具体需求，注意开发者使用python编程，且只能从stdin读取信息，"
#            "从stdout打印运行结果，不能实现图形化。而且测试工程师使用黑盒测试，通过脚本检查开发者代码的输出，"
#            "为了方便测试，你不要给他们过高的要求，只要包含关键点即可，不要写代码"
#        ),
#    )
    
    analyst = OpenAISession(
        api_key=token,
        model=model_analyst,
        system_prompt=(
            "你是需求分析专家。"
            " 用户会给出一个业务或算法需求，你需要：\n"
            " 1. 提炼出清晰的功能描述和约束条件；\n"
            " 2. 明确输入（必须stdin读入，注意格式、数据类型、边界条件）和输出（必须stdout）；\n"
            " 3. 列出可能的异常情况及处理建议；\n"
            " 4. 完整以自然语言输出项目需求要点，需求不要太复杂，禁止编写代码。\n"
            "输出只包含需求分析，使用要点列表，便于开发者快速理解。"
        )
    )


#    developer = SiliconFlowSession(
#        api_key=token,
#        model=model_developer,
#        system_prompt=(
#            "你扮演开发者，根据需求分析师的分析，完成一个python项目（你的代码会保存为solution.py），"
#            "不要包含危险的系统调用，输出只含一段代码，程序的输入全部来自stdin，运行结果输出到stdout。"
#            "写必要的注释，可以输出格式化的调试信息，便于自动化测试。"
#            "测试工程师（也是AI）会写一个黑盒测试脚本以测评你的代码（所以你要严格规范输出格式），"
#            "如果他给你指出错误，你需要修改代码重新输出。"
#        ),
#    )
#    
    developer = OpenAISession(
        api_key=token,
        model=model_developer,
        system_prompt=(
            "你是资深 Python 开发者。"
            " 根据需求分析师提供的需求，要编写一个单文件Python脚本（我会帮你保存为solution.py）：\n"
            " - 仅输出代码，不要有任何额外解释或注释之外的文字；\n"
            " - 所有输入从stdin读取，所有输出写到stdout，输入可选，输出必须；\n"
            " - 禁止任何危险系统调用；\n"
            " - 必要时可添加调试打印（stdout 或 stderr），由于测试工程师会进行黑盒测试，输出格式务必规范化\n"
            " - 要处理常见错误（空输入、格式错误、边界值）；\n"
            "如果测试工程师反馈错误，你将收到错误报告，需修复并重新输出完整脚本。"
        ),
    )
    

#    tester = SiliconFlowSession(
#        api_key=token,
#        model=model_tester,
#        system_prompt=(
#            "你扮演测试工程师，根据需求分析师的描述和开发者提供的代码，生成python测试脚本，"
#            "脚本包含多个测试用例和期望输出，"
#            "和调用开发者代码（可以直接用python3 solution.py调用，他的代码会从stdin输入，从stdout输出）的模块，"
#            "就像online judge的自动化测试一样（可以输出测试信息，便于排查问题）"
#            "如果测试全部通过，返回0，否则返回1。"
#            "你要仔细阅读开发者的代码，注意代码的输出会有不确定性，所以不要过于严格地匹配输出，要增强测试的鲁棒性。"
#            "你只需要提供一个python代码块作为测试脚本。我会帮你保存为test_solution.py并运行。"
#            "如果发现开发者有明显错误，仍然先编写测试脚本。"
#            "注意：如果测试失败，我会把运行结果给你，提示你生成错误报告（分析原因，提供重要信息，但不要帮开发者修改）。"
#            "警告：如果发现是你的测试脚本（test_solution.py）写错了，而非开发者的代码（solution.py）本身有错，"
#            "你就输出\"[[TEST_ERROR]]\"，然后什么都不要说！下一次会话会提示你重新生成完整的测试脚本。"
#            "注意：测试限时60s，如果超时，你要根据问题所在给出符合要求的回答。"
#            "如果测评重复失败，我会给你指令，让你再次生成错误报告，或重新生成测试脚本。"
#        ),
#    )
    
    tester = OpenAISession(
        api_key=token,
        model=model_tester,
        system_prompt=(
            "你是自动化测试工程师。"
            "第一次会话先根据需求分析及开发者代码（solution.py），生成一个 Python 测试脚本，要求：\n"
            " 1. 只输出一个Python代码块，我会帮你保存到为test_solution.py；\n"
            " 2. 调用开发者脚本：python3 solution.py即可，不要有额外操作，任何输入通过stdin，输出通过stdout或stderr；\n"
            " 3. 覆盖典型用例与边界场景，使用容错匹配以增强鲁棒性（例如去除多余空白）；\n"
            " 4. 对每个测试用例打印调试信息，若全部通过调用sys.exit(0)，否则sys.exit(1)；\n"
            " 5. 针对超时（60s）或异常情况捕获并报告。\n"
            "在下一次会话我会把测试脚本运行结果发给你，你有两种选择：\n"
            " 1. 如果测试脚本（test_solution.py）本身有错误，或者你想修改测试脚本，"
            "务必先输出\"<TEST_ERROR>\"标志，然后紧跟新的测试脚本；\n"
            " 2. 如果开发者代码（solution.py）有问题，你就给出错误分析，便于开发者修改，但一定不要帮他写代码。\n"
            "测试不要过于苛刻，不要写无关文字，不允许存在多个代码块。\n"
            "写测试脚本/生成报告的流程会重复多次直到成功。"
        )
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
    dev_code = developing(developer, f"需求描述：\n{analysis}")

    # --- 3. 生成测试脚本 ---
    test_developing(tester, f"需求描述：\n{analysis}\n\n\n开发者代码：\n{dev_code}")


    # --- 4. 测试循环 ---
    for rnd in range(1, 5):
        print(f"\n=== Round {rnd} 运行测试 ===")
        print("### 尝试补全依赖 ###")
        resolver = DependencyResolver(extra_mapping=COMMON_DEP_MAPPING)
        try:
            resolver.install_from_files(["solution.py", "test_solution.py"])
        except Exception as e:
            print(f"### 依赖补全异常 ###\n{e}")
        
        try:
            res = subprocess.run([sys.executable, "test_solution.py"],
                                capture_output=True, text=True, timeout=120)
            time_out = False
            if res.returncode == 0:
                print("---- stdout ----")
                print(res.stdout or "<空>")
                print("---- stderr ----")
                print(res.stderr or "<空>")
                print("🎉 测试全部通过，开发完成！"); break
        except subprocess.TimeoutExpired as e:
            print("---- !测评超时! ----")
            time_out = True
            res = e

        print("---- stdout ----")
        print(res.stdout or "<空>")
        print("---- stderr ----")
        print(res.stderr or "<空>")


        # 让测试工程师生成错误报告
        if time_out:
            report = test_reporting(tester, f"测试超时，运行结果：\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
        else:
            report = test_reporting(tester, f"运行结果：\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")

        if "<test_error>" in report.lower():
            # 测试脚本本身有误
            print("⚠️  测试脚本有误，更新：")
            test_code = extract_code(report)
            print("\n\n--- 测试脚本 (test_solution.py) ---")
            print(test_code)
            input("\n确认后按回车继续…")
            save("test_solution.py", test_code)
            continue

        # 开发者修复代码
        print("❌ 代码需修复…")
        developing(developer, f"错误报告：\n{report}")

    else:
        print("⛔ 达到最大迭代次数，仍未通过测试。")

if __name__ == "__main__":
    main()
