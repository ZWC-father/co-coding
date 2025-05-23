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
        start_time = time()
        result = subprocess.run(['python3', 'solution.py'], 
                              capture_output=True, 
                              text=True,
                              timeout=timeout)

        # Check if output is valid JSON
        try:
            data = json.loads(result.stdout)
            assert isinstance(data, list), "Output should be a JSON array"

            if len(data) > 0:
                first_item = data[0]
                assert 'author' in first_item, "Missing 'author' field"
                assert 'text' in first_item, "Missing 'text' field"
                assert 'tags' in first_item, "Missing 'tags' field"
                assert isinstance(first_item['tags'], list), "'tags' should be a list"

            print("Test 1 passed: Basic output structure is valid")
            passed += 1
        except (json.JSONDecodeError, AssertionError) as e:
            print(f"Test 1 failed: {str(e)}")
            print(f"Output was: {result.stdout[:200]}...")
            failed += 1

    except subprocess.TimeoutExpired:
        print(f"Test 1 failed: Timeout after {timeout} seconds")
        failed += 1
    except Exception as e:
        print(f"Test 1 failed with unexpected error: {str(e)}")
        failed += 1

    # Test 2: Empty case handling (should return empty array)
    try:
        # Mock the response by modifying the URL to non-existent page
        original_code = open('solution.py').read()
        modified_code = original_code.replace(
            'base_url = "http://quotes.toscrape.com"',
            'base_url = "http://nonexistent-quotes-site.example.com"'
        )

        with open('solution_temp.py', 'w') as f:
            f.write(modified_code)

        start_time = time()
        result = subprocess.run(['python3', 'solution_temp.py'], 
                              capture_output=True, 
                              text=True,
                              timeout=timeout)

        try:
            data = json.loads(result.stdout)
            assert data == [], "Should return empty array on error"
            assert "Error fetching data" in result.stderr, "Should log error to stderr"
            print("Test 2 passed: Handles request errors correctly")
            passed += 1
        except (json.JSONDecodeError, AssertionError) as e:
            print(f"Test 2 failed: {str(e)}")
            failed += 1

    except subprocess.TimeoutExpired:
        print(f"Test 2 failed: Timeout after {timeout} seconds")
        failed += 1
    except Exception as e:
        print(f"Test 2 failed with unexpected error: {str(e)}")
        failed += 1
    finally:
        # Restore original file
        with open('solution_temp.py', 'w') as f:
            f.write(original_code)

    # Test 3: Data validation (check field types and cleaning)
    try:
        start_time = time()
        result = subprocess.run(['python3', 'solution.py'], 
                              capture_output=True, 
                              text=True,
                              timeout=timeout)

        try:
            data = json.loads(result.stdout)
            if len(data) > 0:
                for item in data[:5]:  # Check first 5 items
                    assert isinstance(item['author'], str), "Author should be string"
                    assert isinstance(item['text'], str), "Text should be string"
                    assert isinstance(item['tags'], list), "Tags should be list"
                    for tag in item['tags']:
                        assert isinstance(tag, str), "Each tag should be string"
                        assert '\n' not in tag, "Tags should not contain newlines"
                    assert '\n' not in item['text'], "Text should be cleaned"
                    assert not item['text'].startswith('“') and not item['text'].endswith('”'), "Quotes should be stripped"

            print("Test 3 passed: Data validation successful")
            passed += 1
        except (json.JSONDecodeError, AssertionError) as e:
            print(f"Test 3 failed: {str(e)}")
            failed += 1

    except subprocess.TimeoutExpired:
        print(f"Test 3 failed: Timeout after {timeout} seconds")
        failed += 1
    except Exception as e:
        print(f"Test 3 failed with unexpected error: {str(e)}")
        failed += 1

    print(f"\nSummary: {passed} passed, {failed} failed")
    sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    run_test()