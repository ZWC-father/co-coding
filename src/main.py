import os, shutil
from pkg.coding_manager import *
from pkg.utils import *

GREEN = "\x1b[92m"; YELLOW = "\x1b[93m"; RED = "\x1b[91m"; WHITE = "\x1b[97m"; RESET = "\x1b[0m"

def sys_printer(msg_type, msg):
    if msg_type == SYS_OUTPUT_TYPE.debug:
        print(f"{WHITE}{msg}{RESET}", flush=True)
    else:
        print(f"{RED}{msg}{RESET}", flush=True)


def ai_printer(msg_type, msg):
    if msg_type == AI_OUTPUT_TYPE.analyst_resp or msg_type == AI_OUTPUT_TYPE.developer_resp or msg_type == AI_OUTPUT_TYPE.tester_resp:
        print(f"{YELLOW}{msg}{RESET}", end="", flush=True)
    else:
        print(f"{GREEN}{msg}{RESET}", end="", flush=True)


def event_callback(event, manager):
    if event == EVENT_CODE.developing_done:
        print(f"{WHITE}===开发者代码==={RESET}", flush=True)
        print(manager.code)
    elif event == EVENT_CODE.test_developing_done:
        print(f"{WHITE}===测试代码==={RESET}", flush=True)
        print(manager.test_code)
    elif event == EVENT_CODE.testing_done:
        print(f"{WHITE}===测试结果==={RESET}", flush=True)
        print(manager.test_res)
    elif event == EVENT_CODE.reporting_done:
        print(f"{WHITE}===测试报告==={RESET}", flush=True)
        print(manager.report)
    elif event == EVENT_CODE.repairing_done:
        print(f"{WHITE}===修复后的代码==={RESET}", flush=True)
        print(manager.code)
    elif event == EVENT_CODE.done:
        print(f"{WHITE}===运行结果==={RESET}", flush=True)
        print(manager.test_res)
        print("开发完成！")
            

def main():
    token = os.getenv("API_KEY")
    if not token:
        print("API_KEY 未设置")
        sys.exit(1)

    req_file = pathlib.Path("requirement.txt")
    if not req_file.exists():
        print("缺少 requirement.txt")
        sys.exit(1)
    raw_req = req_file.read_text(encoding="utf-8").strip()

    del_path = Path("debug_payloads")
    shutil.rmtree(del_path, ignore_errors=True)

    model_analyst = "deepseek-chat"
    model_developer = "deepseek-chat"
    model_tester = "deepseek-chat"

    
    analyst = OpenAISession(
        base_url="https://api.deepseek.com/",
        api_key=token,
        model=model_analyst
    )

    developer = OpenAISession(
        base_url="https://api.deepseek.com/",
        api_key=token,
        model=model_developer,
        extra_params={"temperature": 0.5}
    )
    
    tester = OpenAISession(
        base_url="https://api.deepseek.com/",
        api_key=token,
        model=model_tester,
        extra_params={"temperature": 0.5}
    )
    
    manager = CodingManager(raw_req, analyst, developer, tester,
                             sys_output_callback=sys_printer, ai_output_callback=ai_printer, event_callback=event_callback)

    while not manager.step():
        input("按Enter下一步")


if __name__ == "__main__":
    main()
