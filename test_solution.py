import sys
import subprocess
from subprocess import TimeoutExpired

test_cases = [
    # Valid cases
    {"input": ["aab", "c*a*b"], "output": "true", "desc": "Example 1"},
    {"input": ["aa", "a"], "output": "false", "desc": "Example 2"},
    {"input": ["", "a*"], "output": "true", "desc": "Empty s with a*"},
    {"input": ["", ""], "output": "true", "desc": "Both empty"},
    {"input": ["abc", ".*"], "output": "true", "desc": "Dot-star match"},
    {"input": ["aaa", "a*a"], "output": "true", "desc": "Middle star match"},
    {"input": ["ab", ".*.."], "output": "true", "desc": "Multiple dots with star"},
    {"input": ["a", "ab*"], "output": "true", "desc": "Trailing star zero match"},
    {"input": ["mississippi", "mis*is*p*."], "output": "false", "desc": "Complex non-match"},

    # Edge cases
    {"input": ["a"*20, "a*a*a*a*a*a*a*a*a*a"], "output": "true", "desc": "Max length s and p"},
    {"input": ["", "a*b*c*"], "output": "true", "desc": "Multiple stars empty s"},

    # Error cases
    {"input": ["aa", "*a"], "error": True, "desc": "Pattern starts with *"},
    {"input": ["a", "a**b"], "error": True, "desc": "Consecutive stars"},
    {"input": ["a", "aA"], "error": True, "desc": "Invalid pattern char"},
    {"input": ["a"], "error": True, "desc": "Insufficient lines"},
]

all_passed = True

for case in test_cases:
    input_data = '\n'.join(case["input"]) + '\n'
    proc = subprocess.Popen(
        ["python3", "solution.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    try:
        stdout, stderr = proc.communicate(input=input_data, timeout=5)
        stdout = stdout.strip()
        stderr = stderr.strip()

        if case.get("error"):
            if proc.returncode == 1 and "error" in stderr:
                print(f"PASS: {case['desc']}")
            else:
                all_passed = False
                print(f"FAIL: {case['desc']} (Expected error, got: stdout={stdout}, stderr={stderr}, rc={proc.returncode})")
        else:
            if proc.returncode != 0:
                all_passed = False
                print(f"FAIL: {case['desc']} (Exited with code {proc.returncode}, stderr={stderr})")
            elif stdout == case["output"]:
                print(f"PASS: {case['desc']}")
            else:
                all_passed = False
                print(f"FAIL: {case['desc']} (Expected '{case['output']}', got '{stdout}')")
    except TimeoutExpired:
        all_passed = False
        proc.kill()
        stdout, stderr = proc.communicate()
        print(f"FAIL: {case['desc']} (Timeout)")

sys.exit(0 if all_passed else 1)