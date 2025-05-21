import sys
import os
import subprocess
from io import StringIO

def run_test(input_data, expected_output):
    """Run the test and compare with expected output."""
    # Redirect stdin for the subprocess
    original_stdin = sys.stdin
    sys.stdin = StringIO(input_data)

    # Capture stdout
    original_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        # Import and run the solution module
        import solution
        solution.main()
    finally:
        # Restore stdin/stdout
        output = sys.stdout.getvalue().strip()
        sys.stdin = original_stdin
        sys.stdout = original_stdout

    # Compare results
    if str(output) == str(expected_output):
        print(f"PASSED: Input: {input_data.strip()} -> Output: {output}")
        return True
    else:
        print(f"FAILED: Input: {input_data.strip()}")
        print(f"  Expected: {expected_output}")
        print(f"  Got:      {output}")
        return False

def main():
    # Test cases
    test_cases = [
        # Simple connected graph
        {
            "input": "3 3\n1 2 5\n2 3 3\n1 3 1",
            "output": "4"
        },
        # Graph with self-loop (should be discarded)
        {
            "input": "3 4\n1 2 5\n2 2 10\n2 3 3\n1 3 1",
            "output": "4"
        },
        # Disconnected graph
        {
            "input": "4 2\n1 2 5\n3 4 3",
            "output": "-1"
        },
        # Single node graph
        {
            "input": "1 0",
            "output": "-1"
        },
        # Graph with multiple edges between same nodes
        {
            "input": "3 4\n1 2 5\n1 2 3\n2 3 4\n1 3 6",
            "output": "7"
        },
        # Large graph with node numbers starting at 0
        {
            "input": "4 5\n0 1 1\n1 2 2\n2 3 3\n0 3 4\n0 2 5",
            "output": "6"
        },
        # All nodes isolated (no edges)
        {
            "input": "3 0",
            "output": "-1"
        },
        # Complex graph
        {
            "input": "5 7\n1 2 10\n1 3 20\n2 3 30\n2 4 5\n3 4 15\n3 5 6\n4 5 8",
            "output": "29"
        }
    ]

    all_passed = True
    for i, test_case in enumerate(test_cases, 1):
        if not run_test(test_case["input"], test_case["output"]):
            all_passed = False

    if all_passed:
        print("\nAll tests passed!")
        sys.exit(0)
    else:
        print("\nSome tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()