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
    question_done：需求分析师完成提问，你要根据追问完善需求描述
    analyzing_done：需求分析完成，下一步是开发
    developing_done：开发完成，下一步是测试
    test_developing_done：测试脚本开发完成，下一步运行测试代码
    testing_done：测试完成（但是未通过），下一步会让测试工程师生成错误报告
    reporting_done：报告完成，下一步会让开发者修改代码或者重新运行测试（如果测试脚本本身有错误）
    repairing_done：修复完成，下一步重新运行测试
    done：整个开发过程完成

    CodingManager还提供一个函数get_stage()，
    用于判断当前的状态，返回值为INTERNAL_STAGE枚举类型。
    具体定义查看coding_manager.py

    不要在回调函数中调用step()和chat()
    """
    if event == EVENT_CODE.question_done:
        print(f"{WHITE}===需求分析追问==={RESET}", flush=True)
        print(manager.question)
    elif event == EVENT_CODE.analyzing_done:
        print(f"{WHITE}===需求分析==={RESET}", flush=True)
        print(manager.analysis)
    elif event == EVENT_CODE.developing_done:
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

    del_path = Path("debug_payloads") #删除上一次的请求体内容
    shutil.rmtree(del_path, ignore_errors=True) #生成请求体调试信息的代码在api_session.py

    model_analyst = "deepseek-r1-0528"
    model_developer = "deepseek-r1-0528"
    model_tester = "deepseek-r1-0528" #分别设置三人的模型
    #建议给analyst也使用最强的模型
    
    analyst = OpenAISession(
        base_url="https://api.lkeap.cloud.tencent.com/v1", #此处改为使用腾讯云api
        api_key=token,
        model=model_analyst,
        extra_params={"temperature": 0.4}
    )

    developer = OpenAISession(
        base_url="https://api.lkeap.cloud.tencent.com/v1",
        api_key=token,
        model=model_developer,
        extra_params={"temperature": 0.4} #设置采样温度
    )
    
    tester = OpenAISession(
        base_url="https://api.lkeap.cloud.tencent.com/v1",
        api_key=token,
        model=model_tester,
        extra_params={"temperature": 0.4}
    )
    
    """
    analyst/developer/tester：三人对应的的模型实例
    sys_output_callback：系统输出回调，用于传递系统信息
    ai_output_callback：模型输出回调，采用流式输出，用于输出ai的思考和输出原始内容
    event_callback：事件回调，传递系统事件
    """
    manager = CodingManager(analyst=analyst, developer=developer, tester=tester,
                            sys_output_callback=sys_printer, ai_output_callback=ai_printer, event_callback=event_callback)
    


    """
    第一次调用chat()给出开发需求，使用方法和step()基本一样，如果需求分析师认为你需要补充，chat()就会返回True，
    否则返回False，你就要从manager.question获取问题，此处把输出问题的逻辑改到event_callback中实现
    注意chat()也可能抛出异常
    """
    user_input = ""
    user_input = input("输入需求：")
    while not manager.chat(user_input):
        user_input = input("请回答问题：") 
    input("按Enter下一步")
    

    """
    调用step()开始下一步开发操作，注意step是同步阻塞调用，返回False表示没有完成开发，还需要进行下一步，如果返回True表示开发成功或者被中断
    调用stop()可以中断开发并使step返回True或者抛出GenerationInterrupted，所以谨慎调用stop()（因为没有实现线程安全），
    如果因为网络中断造成生成卡住，调用stop()并不会让step()立即返回（因为没有使用异步IO）。
    """
    while not manager.step():
        input("按Enter下一步")

    
    """
    重要：异常捕获
    可能出现的异常类型：
    DependencyError：依赖自动补全失败，这种情况需要用户手动补全(在venv中执行依赖补全命令)，再调用step即可重新运行测试，继续开发过程
    DevelopConflict：开发者和测试工程师意见冲突，通常因为开发者认为自己的代码没问题，而测试工程师不通过
    DevelopRefused：开发被拒绝，通常因为需求不合理
    GenrationInterrupted：生成被打断，如果调用模型正在生成，调用stop()，step()就会抛出这个异常，
    其他类型异常：可能因为文件操作异常，网络错误，api请求超时（60s）等等
    除了第一种异常，其他异常均无法继续开发过程，manager实例也处于无效状态，不能再调用step，一切需要重新开始
    """

    """
    注意所有API为同步阻塞调用，没有线程安全保证
    chat()和step()一旦返回True，表明需求分析/开发(测试)工作已经完成，不能再重复调用
    即manager和三个模型实例(model_*)都是一次性的，无论是意外中断，还是正常开发结束，都会处于无效状态
    """

if __name__ == "__main__":
    main()
