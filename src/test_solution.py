import sys
import json
import subprocess
from time import time

def run_test():
    passed = 0
    failed = 0
    timeout = 60

    # Test 1: Basic functionality check
    try:
        start = time()
        result = subprocess.run(['python3', 'solution.py'], 
                              capture_output=True, text=True, timeout=timeout)
        elapsed = time() - start

        if result.returncode != 0:
            print(f"❌ Test 1 Failed (Runtime Error)\nSTDERR:\n{result.stderr}")
            failed += 1
        else:
            try:
                data = json.loads(result.stdout)
                if not isinstance(data, list):
                    print("❌ Test 1 Failed: Output is not a JSON array")
                    failed += 1
                elif len(data) < 10:
                    print(f"❌ Test 1 Failed: Expected >=10 quotes, got {len(data)}")
                    failed += 1
                else:
                    valid = True
                    for item in data[:3]:  # Check first 3 items
                        if not all(k in item for k in ['text', 'author', 'tags']):
                            valid = False
                            break
                        if not isinstance(item['tags'], list):
                            valid = False
                            break
                    if valid:
                        print(f"✅ Test 1 Passed (Got {len(data)} quotes in {elapsed:.2f}s)")
                        passed += 1
                    else:
                        print("❌ Test 1 Failed: Missing required fields in items")
                        failed += 1
            except json.JSONDecodeError:
                print(f"❌ Test 1 Failed: Invalid JSON output\n{result.stdout[:200]}...")
                failed += 1
    except subprocess.TimeoutExpired:
        print(f"❌ Test 1 Failed: Timeout after {timeout} seconds")
        failed += 1

    # Test 2: Data completeness check
    try:
        start = time()
        result = subprocess.run(['python3', 'solution.py'], 
                              capture_output=True, text=True, timeout=timeout)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            empty_fields = 0
            for item in data:
                if not item.get('text') or not item.get('author'):
                    empty_fields += 1

            if empty_fields == 0:
                print("✅ Test 2 Passed (All quotes have text and author)")
                passed += 1
            else:
                print(f"❌ Test 2 Failed: {empty_fields} quotes missing text/author")
                failed += 1
    except:
        print("❌ Test 2 Failed: Could not validate data completeness")
        failed += 1

    # Test 3: Pagination check (verify multi-page scraping)
    try:
        start = time()
        result = subprocess.run(['python3', 'solution.py'], 
                              capture_output=True, text=True, timeout=timeout)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            if len(data) > 20:  # Site should have >20 quotes total
                print(f"✅ Test 3 Passed (Multi-page scraping worked, got {len(data)} quotes)")
                passed += 1
            else:
                print(f"❌ Test 3 Failed: Expected >20 quotes, got {len(data)} (possible pagination issue)")
                failed += 1
    except:
        print("❌ Test 3 Failed: Could not validate pagination")
        failed += 1

    # Summary
    print(f"\nSummary: {passed} passed, {failed} failed")
    return failed == 0

if __name__ == "__main__":
    if run_test():
        sys.exit(0)
    else:
        sys.exit(1)