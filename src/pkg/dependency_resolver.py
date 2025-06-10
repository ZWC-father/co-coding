import re, subprocess, ast
from pathlib import Path
from typing import List

def contains_phrase(text: str, phrase: str) -> bool:
    """
    在只含 ASCII 的文本中查找含空格的子串。
    1. 将连续空白折叠成一个空格；
    2. 两端去空格；
    3. 直接用 `in` 或简易正则查找。
    """
    # 统一空白为单个空格
    text_norm   = re.sub(r'\s+', ' ', text).strip()
    phrase_norm = re.sub(r'\s+', ' ', phrase).strip()
    # 直接包含判断
    return phrase_norm in text_norm

class DependencyResolver:
    """
    扫描 Python 源文件中的 import 语句，识别缺失的第三方包，
    并在当前 venv 中通过 pip 安装它们。

    usage:
        resolver = DependencyResolver()
        resolver.install_from_files(["solution.py", "test_solution.py"])
    """

    def __init__(self):
        # 保留属性以兼容旧接口
        self.mapping = {}

    def _generate_requirements(self, project_path: str) -> List[str]:
        """
        调用 pipreqs 生成依赖列表；使用 --print 参数确保无交互。
        """
        try:
            result = subprocess.run(
                    ["pipreqs", project_path, "--print", "--pypi-server", "https://mirrors.sdu.edu.cn/pypi/pypi/"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            if contains_phrase(result.stderr, "does not exist"):
                raise RuntimeError(f"依赖生成失败（pipreqs）：\n{result.stderr.strip()}")
 
            # 每行即一个包名
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"依赖生成失败（pipreqs）：\n{e.stderr.strip()}"
            ) from e
        except FileNotFoundError:
            raise RuntimeError(
                "pipreqs 未安装或不可执行，请先运行 pip install pipreqs"
            )

    def _is_installed(self, module: str) -> bool:
        """
        判断包是否已安装。仅检查模块名对应的分发包是否可 import。
        """
        import importlib.util
        return importlib.util.find_spec(module) is not None

    def _install_package(self, package: str) -> None:
        """
        使用 pip 安装单个包；失败则抛出 RuntimeError。
        """
        cmd = ["pip", "install", package]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"依赖安装失败：{package} (exit {e.returncode})") from e

    def test_from_file(self, path: str) -> bool:
        import importlib
        with open(path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=path)

        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module)

        for m in sorted(mods):
            try:
                importlib.import_module(m)
            except ImportError:
                return False

        return True


    def install_from_files(self) -> None:
        """
        扫描文件并使用 pipreqs 自动生成、安装缺失依赖（接口保持不变）。
        """
        # 假设脚本在项目根目录下执行；也可根据 filepaths 动态计算根目录
        project_root = str(Path.cwd())

        # 生成依赖列表
        to_install = self._generate_requirements(project_root)

        # 过滤已安装包
        filtered = []
        for pkg in to_install:
            # 对于像 "requests==2.28.1" 带版本的需求，仅取包名部分进行检测
            name = pkg.split("==", 1)[0]
            if not self._is_installed(name):
                filtered.append(pkg)

        # 若无新依赖，提前返回
        if not filtered:
            return

        # 安装所有缺失依赖
        for pkg in filtered:
            self._install_package(pkg)

