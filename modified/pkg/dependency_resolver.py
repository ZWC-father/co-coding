import sys, subprocess, ast
import importlib.util
from pathlib import Path
from typing import List, Set

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

    def __init__(self):
        """
        :param extra_mapping: 可选的模块名到 pip 包名映射，
                              例如 {"yaml": "pyyaml"}。
        """
        self.mapping = COMMON_DEP_MAPPING

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
            #print("🎉 未发现需要安装的新依赖。")
            return

        #print("🔍 发现新依赖，开始安装：", to_install)
        for pkg in to_install:
            self._install_package(pkg)
        #print("✅ 依赖安装完成！")

