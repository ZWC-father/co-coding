import sys, os, shutil
from pkg.coding_manager import * # 导入CodingManager类
from pkg.utils import *

GREEN = "\x1b[92m"; YELLOW = "\x1b[93m"; RED = "\x1b[91m"; WHITE = "\x1b[97m"; RESET = "\x1b[0m"
#控制不同文本的输出颜色，在Windows下无效，可以删掉，避免乱码

def sys_printer(msg_type, msg):
    """
    系统输出消息：
    debug表示调试信息，仅仅输出tokens使用情况
    info输出状态信息
    """
    if msg_type == SYS_OUTPUT_TYPE.debug:
        print(f"{WHITE}{msg}{RESET}", flush=True)
    else:
        print(f"{RED}{msg}{RESET}", flush=True)


def ai_printer(msg_type, msg):
    """
    msg_type：消息类型 (Enum)
    msg：消息（str）

    上游会流式响应，所以你应当及时刷新缓冲区
    *_think：对应三个人的思考输出
    *_resp：对应三个人的回答输出
    可以对响应消息实时进行markdone渲染
    """
    if msg_type == AI_OUTPUT_TYPE.analyst_resp or msg_type == AI_OUTPUT_TYPE.developer_resp or msg_type == AI_OUTPUT_TYPE.tester_resp:
        print(f"{YELLOW}{msg}{RESET}", end="", flush=True)
    else:
        print(f"{GREEN}{msg}{RESET}", end="", flush=True)


def event_callback(event, manager):
    """
    event：事件类型（Enum）
    manager：CodingManager实例，方便访问CodingManager成员
    
    事件类型说明：
    developing_done：开发完成（下一步是测试）
    test_developing_done：测试脚本开发完成（下一步运行测试代码）
    testing_done：测试完成（但是未通过），下一步会让测试工程师生成错误报告
    reporting_done：报告完成，下一步会让开发者修改代码或者重新运行测试（如果测试脚本本身有错误）
    repairing_done：修复完成，下一步重新运行测试
    done：整个开发过程完成

    CodingManager还提供一个函数get_stage()，
    用于判断当前的状态，返回值为INTERNAL_STAGE枚举类型。
    具体定义查看coding_manager.py
    """
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
        print("===开发完成===")
            

def main():
    token = os.getenv("API_KEY") #设置api token，默认从环境变量导入
    if not token:
        print("API_KEY 未设置")
        sys.exit(1)

    req_file = pathlib.Path("requirement.txt") #从文件读取开发需求
    if not req_file.exists():
        print("缺少 requirement.txt")
        sys.exit(1)
    raw_req = req_file.read_text(encoding="utf-8").strip()

    del_path = Path("debug_payloads")
    shutil.rmtree(del_path, ignore_errors=True)

    model_analyst = "deepseek-chat"
    model_developer = "deepseek-chat"
    model_tester = "deepseek-chat" #分别设置三人的模型
    
    analyst = OpenAISession(
        base_url="https://api.deepseek.com/", #此处以deepseek官方api为例
        api_key=token,
        model=model_analyst
    )

    developer = OpenAISession(
        base_url="https://api.deepseek.com/",
        api_key=token,
        model=model_developer,
#       extra_params={"temperature": 0.6} #设置采样温度，默认不需要修改，deepseek-reasoner模型也不支持这个参数
    )
    
    tester = OpenAISession(
        base_url="https://api.deepseek.com/",
        api_key=token,
        model=model_tester,
#       extra_params={"temperature": 0.6}
    )
    
    manager = CodingManager(requirement=raw_req, analyst=analyst, developer=developer, tester=tester,
                             sys_output_callback=sys_printer, ai_output_callback=ai_printer, event_callback=event_callback)
    """
    raw_req：原始开发需求
    analyst/developer/tester：三人对应的的模型实例
    sys_output_callback：系统输出回调，用于传递系统信息
    ai_output_callback：模型输出回调，采用流式输出，用于输出ai的思考和输出原始内容
    event_callback：事件回调，传递系统事件
    """

    while not manager.step():
        input("按Enter下一步")
    
    """
    调用step()进行下一步操作，注意step是同步阻塞调用，返回False表示没有完成开发，还需要进行下一步，如果返回True表示开发成功或者被中断
    调用stop()可以中断开发并使step返回True或者抛出GenerationInterrupted，所以谨慎调用stop()（因为没有实现线程安全），
    如果因为网络中断造成生成卡住，调用stop()并不会让step()立即返回（因为没有使用异步IO）。
    """

    """
    重要：异常捕获
    可能出现的异常类型：
    DependencyError：依赖自动补全失败，这种情况需要用户手动补全，再调用step即可重新运行测试，继续开发过程
    DevelopConflict：开发者和测试工程师意见冲突，通常因为开发者认为自己的代码没问题，而测试工程师不通过
    DevelopRefused：开发被拒绝，通常因为需求不合理
    GenrationInterrupted：生成被打断，如果调用模型正在生成，调用stop()，step()就会抛出这个异常，
    其他类型异常：可能因为文件操作异常，网络错误，api请求超时（60s）等等
    除了第一种异常，其他异常均无法继续开发过程，manager实例也处于无效状态，不能再调用step，一切需要重新开始
    上述异常通常只会从step()处抛出
    """

    """
    注意所有API为同步阻塞调用，没有线程安全保证
    """


if __name__ == "__main__":
    main()
