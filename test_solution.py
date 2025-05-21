import subprocess
import sys

def run_test(test_name, input_data, expected_output):
    try:
        process = subprocess.run(
            ['python3', 'solution.py'],
            input=input_data.encode(),
            capture_output=True,
            text=True,
            check=True
        )
        if process.stdout.strip() == expected_output:
            print(f"[PASS] {test_name}")
            return True
        else:
            print(f"[FAIL] {test_name}")
            print(f"Input:\n{input_data}")
            print(f"Expected:\n{expected_output}")
            print(f"Got:\n{process.stdout}")
            return False
    except Exception as e:
        print(f"[ERROR] {test_name}")
        print(f"Exception: {str(e)}")
        return False

def main():
    test_cases = [
        {
            "name": "Normal input",
            "input": "3\n3 1 2\n",
            "expected": "1 2 3"
        },
        {
            "name": "Single element",
            "input": "1\n5\n",
            "expected": "5"
        },
        {
            "name": "All same elements",
            "input": "2\n3 3\n",
            "expected": "3 3"
        },
        {
            "name": "Negative numbers",
            "input": "3\n-5 0 3\n",
            "expected": "-5 0 3"
        },
        {
            "name": "Mixed numbers",
            "input": "4\n4 -2 0 5\n",
            "expected": "-2 0 4 5"
        }
    ]
    
    all_passed = True
    for test in test_cases:
        if not run_test(test["name"], test["input"], test["expected"]):
            all_passed = False
    
    if not all_passed:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()