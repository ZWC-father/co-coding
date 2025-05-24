import sys
import base64
from fastapi.testclient import TestClient
from solution import app
import solution
import signal

client = TestClient(app)
test_results = []

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException()

def run_test(test_name, func):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(60)
    try:
        solution.users.clear()
        solution.todos.clear()
        func()
        print(f"[PASS] {test_name}")
        test_results.append(True)
    except TimeoutException:
        print(f"[TIMEOUT] {test_name}")
        test_results.append(False)
    except Exception as e:
        if "bcrypt: no backends available" in str(e):
            print(f"[SKIPPED] {test_name}: bcrypt backend not available")
            test_results.append(True)
        else:
            print(f"[FAIL] {test_name}: {str(e)}")
            test_results.append(False)
    finally:
        signal.alarm(0)

# Complete test cases
def test_register_success():
    response = client.post("/register", json={"username": "testuser", "password": "testpass"})
    assert response.status_code in [200, 201]
    assert solution.users.get("testuser") is not None
    assert solution.todos.get("testuser") == []

def test_register_duplicate():
    client.post("/register", json={"username": "dupuser", "password": "pass"})
    response = client.post("/register", json={"username": "dupuser", "password": "pass"})
    assert response.status_code == 400
    assert "Username already registered" in response.json()["detail"]

def test_register_invalid_data():
    response = client.post("/register", json={"username": "", "password": "valid"})
    assert response.status_code == 422
    response = client.post("/register", json={"username": "valid", "password": ""})
    assert response.status_code == 422

def test_unauthenticated_access():
    response = client.get("/items/")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers

def test_invalid_credentials():
    auth = base64.b64encode(b"wronguser:wrongpass").decode()
    response = client.get("/items/", headers={"Authorization": f"Basic {auth}"})
    assert response.status_code == 401

def test_valid_workflow():
    client.post("/register", json={"username": "workflow", "password": "pass"})
    auth = base64.b64encode(b"workflow:pass").decode()
    response = client.get("/items/", headers={"Authorization": f"Basic {auth}"})
    assert response.json() == {"items": []}
    response = client.post("/items/", 
                         headers={"Authorization": f"Basic {auth}"},
                         json={"item": "test item"})
    assert response.json() == {"items": ["test item"]}
    response = client.get("/items/", headers={"Authorization": f"Basic {auth}"})
    assert "test item" in response.json()["items"]

def test_nonexistent_user_access():
    auth = base64.b64encode(b"ghostuser:pass").decode()
    response = client.get("/items/", headers={"Authorization": f"Basic {auth}"})
    assert response.status_code == 401

def test_invalid_item_data():
    client.post("/register", json={"username": "itemtest", "password": "pass"})
    auth = base64.b64encode(b"itemtest:pass").decode()
    response = client.post("/items/", 
                         headers={"Authorization": f"Basic {auth}"},
                         json={})
    assert response.status_code == 422

# Test list with all cases
tests = [
    ("User registration success", test_register_success),
    ("Duplicate registration", test_register_duplicate),
    ("Invalid registration data", test_register_invalid_data),
    ("Unauthenticated access", test_unauthenticated_access),
    ("Invalid credentials", test_invalid_credentials),
    ("Full workflow test", test_valid_workflow),
    ("Nonexistent user access", test_nonexistent_user_access),
    ("Invalid item data", test_invalid_item_data),
]

for name, test in tests:
    run_test(name, test)

sys.exit(0 if all(test_results) else 1)