import re, textwrap, pathlib
from typing import List

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


def save(path: str, content: str):
    pathlib.Path(path).write_text(content, encoding="utf-8")

