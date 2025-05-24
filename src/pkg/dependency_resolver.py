import sys, subprocess, ast
import importlib.util
from pathlib import Path
from typing import List, Set

COMMON_DEP_MAPPING = {
    # Web 爬虫 / 解析
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "html5lib": "html5lib",
    "xmltodict": "xmltodict",
    "markdown": "Markdown",
    "mistune": "mistune",
    # 图像处理
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "imageio": "imageio",
    "skimage": "scikit-image",
    # 数据科学 与 机器学习
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "statsmodels": "statsmodels",
    "sympy": "sympy",
    "tensorflow": "tensorflow",
    "torch": "torch",
    "keras": "keras",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
    "gensim": "gensim",
    "nltk": "nltk",
    "spacy": "spacy",
    "cvxpy": "cvxpy",
    # 可视化
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "bokeh": "bokeh",
    "altair": "altair",
    "dash": "dash",
    # 网络 请求
    "requests": "requests",
    "urllib3": "urllib3",
    "aiohttp": "aiohttp",
    "httpx": "httpx",
    "selenium": "selenium",
    "paramiko": "paramiko",
    "pycurl": "pycurl",
    # 安全 / 加密
    "Crypto": "pycryptodome",
    "cryptography": "cryptography",
    "pyOpenSSL": "pyOpenSSL",
    "hashlib": "hashlib",  # stdlib
    # 数据库 连接
    "sqlalchemy": "SQLAlchemy",
    "psycopg2": "psycopg2-binary",
    "pymysql": "PyMySQL",
    "mysql.connector": "mysql-connector-python",
    "pymongo": "pymongo",
    "redis": "redis",
    "elasticsearch": "elasticsearch",
    # 异步 框架
    "django": "Django",
    "flask": "Flask",
    "fastapi": "fastapi",
    "tornado": "tornado",
    "starlette": "starlette",
    "quart": "quart",
    "uvicorn": "uvicorn",
    # 缓存、消息队列
    "kombu": "kombu",
    "celery": "celery",
    "rabbitpy": "rabbitpy",
    "kafka": "kafka-python",
    "pika": "pika",
    # 云服务 SDK
    "boto3": "boto3",
    "botocore": "botocore",
    "googleapiclient": "google-api-python-client",
    "azure.storage.blob": "azure-storage-blob",
    "azure.identity": "azure-identity",
    # 测试 相关
    "pytest": "pytest",
    "unittest": "unittest",  # stdlib
    "nose": "nose",
    "coverage": "coverage",
    "mock": "mock",
    "tox": "tox",
    # 文档 与 构建
    "sphinx": "Sphinx",
    "mkdocs": "mkdocs",
    "docutils": "docutils",
    "twine": "twine",
    "wheel": "wheel",
    "setuptools": "setuptools",
    # 开发 工具
    "flake8": "flake8",
    "pylint": "pylint",
    "black": "black",
    "isort": "isort",
    "mypy": "mypy",
    "pre-commit": "pre-commit",
    # 便利 工具
    "tqdm": "tqdm",
    "click": "click",
    "rich": "rich",
    "colorama": "colorama",
    "tabulate": "tabulate",
    "python-dotenv": "python-dotenv",
    "schedule": "schedule",
    "retrying": "retrying",
    "filelock": "filelock",
    # 可视化图/图论
    "networkx": "networkx",
    "graphviz": "graphviz",
    "pydot": "pydot",
    "pygraphviz": "pygraphviz",
    # 并发 与 事件驱动
    "gevent": "gevent",
    "eventlet": "eventlet",
    "twisted": "Twisted",
    # 科学 与 大数据
    "pyarrow": "pyarrow",
    "fastparquet": "fastparquet",
    "pyspark": "pyspark",
    # Azure / AWS / GCP 客户端也可类推
    # 其他 常见库
    "ruamel.yaml": "ruamel.yaml",
    "yaml": "PyYAML",
    "arrow": "arrow",
    "dateutil": "python-dateutil",
    "pytz": "pytz",
    "python-dateutil": "python-dateutil",
    "six": "six",
    "pathlib": "pathlib",  # stdlib backport for Py2
    "dataclasses": "dataclasses",
    "structlog": "structlog",
    "loguru": "loguru",
    # 第三方 UI / GUI
    "PyQt5": "PyQt5",
    "wx": "wxPython",
    "kivy": "kivy",
    "pygame": "pygame",
    # 专用 数据格式
    "simplejson": "simplejson",
    "ujson": "ujson",
    "python-rapidjson": "python-rapidjson",
    "chardet": "chardet",
    "charset_normalizer": "charset-normalizer",
    "pycparser": "pycparser",
    "cffi": "cffi",
    # 实用 工具
    "SQLAlchemy-Utils": "SQLAlchemy-Utils",
    "alembic": "alembic",
    "prometheus_client": "prometheus-client",
    "paho.mqtt.client": "paho-mqtt",
    "wmi": "wmi",
    "notebook": "notebook",
    "jupyter": "jupyter",
    "jupyterlab": "jupyterlab",
    "ipython": "ipython",
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

