from __future__ import annotations
import sys, subprocess
from typing import Callable
from enum import Enum
from .api_session import *
from .utils import *
from .dependency_resolver import *

analyst_system_prompt=(
    "你是需求分析专家。"
    "用户会给出一个业务或算法需求，你需要：\n"
    "1. 提炼出清晰的功能描述和约束条件；\n"
    "2. 明确输入（必须stdin读入，注意格式、数据类型、边界条件）和输出（必须stdout）；\n"
    "3. 列出可能的异常情况及处理建议；\n"
    "4. 完整以自然语言输出项目需求要点，需求不要太复杂，禁止编写代码。\n"
    "输出只包含需求分析，使用要点列表，便于开发者快速理解。"
)

developer_system_prompt=(
    "你是资深 Python 开发者。"
    "根据需求分析师提供的需求，要编写一个单文件Python脚本（我会帮你保存为solution.py）：\n"
    "1. 仅输出代码，不要有任何额外解释或注释之外的文字；\n"
    "2. 所有输入从stdin读取，所有输出写到stdout，输入可选，输出必须；\n"
    "3. 禁止任何危险系统调用；\n"
    "4. 必要时可添加调试打印（stdout 或 stderr），由于测试工程师会进行黑盒测试，输出格式务必规范化\n"
    "5. 要处理常见错误（空输入、格式错误、边界值）；\n"
    "如果测试工程师（也是AI）反馈错误，你将收到错误报告，需修复并重新输出完整脚本。\n"
    "如果你认为测试工程师的测试不合理，请输出<TEST_ERROR>标志告诉我。"
)

tester_system_prompt=(
    "你是自动化测试工程师。"
    "第一次会话先根据需求分析及开发者代码（solution.py），生成一个 Python 测试脚本，要求：\n"
    "1. 只输出一个Python代码块，我会帮你保存到为test_solution.py；\n"
    "2. 调用开发者脚本：python3 solution.py即可，不要有额外操作，任何输入通过stdin，输出通过stdout或stderr；\n"
    "3. 覆盖典型用例与边界场景，使用容错匹配以增强鲁棒性（例如去除多余空白）；\n"
    "4. 对每个测试用例打印调试信息，若全部通过调用sys.exit(0)，否则sys.exit(1)；\n"
    "5. 针对超时（60s）或异常情况捕获并报告。\n"
    "在下一次会话我会把测试脚本运行结果发给你，你有两种选择：\n"
    "1. 如果测试脚本（test_solution.py）本身有错误，或者你想修改测试脚本，务必先输出\"<TEST_ERROR>\"标志，然后紧跟新的测试脚本；\n"
    "2. 如果开发者代码（solution.py）有问题，你就给出错误分析，便于开发者修改，但一定不要帮他写代码。\n"
    "测试不要过于苛刻，不要写无关文字，不允许存在多个代码块。\n"
    "写测试脚本/生成报告的流程会重复多次直到成功。"
)

class DevelopConflict(Exception):
    pass

class DevelopRefuse(Exception):
    pass

class AI_OUTPUT_TYPE(Enum):
    analyst_think = 1
    analyst_resp = 2
    developer_think = 3
    developer_resp = 4
    tester_think = 5
    tester_resp = 6

class SYS_OUTPUT_TYPE(Enum):
    debug = 1
    info = 2

class EVENT_CODE(Enum):
    done = 0
    analyzing_done = 1
    developing_done = 2
    test_developing_done = 3
    testing_done = 4
    reporting_done = 5
    repairing_done = 6

class INTERNAL_STAGE(Enum):
    need_analyzing = 0
    need_developing = 1
    need_test_developing = 2
    need_testing = 3
    need_reporting = 4
    need_repairing = 5

class CodingManager:
    def __init__(self,
                 requirement: str,
                 analyst: OpenAISession,
                 developer: OpenAISession,
                 tester: OpenAISession,
                 ai_output_callback: Callable[[AI_OUTPUT_TYPE, str], None],
                 sys_output_callback: Callable[[SYS_OUTPUT_TYPE, str], None],
                 event_callback: Callable[[EVENT_CODE, CodingManager], None]
                 ):
        self._requirement = requirement
        self._analyst = analyst
        self._developer = developer
        self._tester = tester
        self._ai_output_calllback = ai_output_callback
        self._sys_output_callback = sys_output_callback
        self._event_callback = event_callback
        
        self._stage = INTERNAL_STAGE.need_analyzing
        self.analysis = ""
        self.code = ""
        self.test_code = ""
        self.test_res = ""
        self.report = ""

        self._code_repaired = False
        
        self._analyst.set_sys_prompt(analyst_system_prompt)
        self._developer.set_sys_prompt(developer_system_prompt)
        self._tester.set_sys_prompt(tester_system_prompt)
        
    def get_stage(self):
        return self._stage

    def step(self) -> bool:
        if self._stage == INTERNAL_STAGE.need_analyzing:
            self._analyzing()
        elif self._stage == INTERNAL_STAGE.need_developing:
            self._developing(f"需求描述：\n{self.analysis}")
        elif self._stage == INTERNAL_STAGE.need_test_developing:
            self._tester_developing(f"需求描述：\n{self.analysis}\n\n\n开发者代码：\n{self.code}")
        elif self._stage == INTERNAL_STAGE.need_testing:
            return self._testing()
        elif self._stage == INTERNAL_STAGE.need_reporting:
            self._tester_reporting(f"运行结果：\n{self.test_res}")
        elif self._stage == INTERNAL_STAGE.need_repairing:
            self._repairing(f"错误报告：\n{self.report}")

        return False
            

    def _cb_ai(self, msg_type):
        def __cb(msg):
            self._ai_output_calllback(msg_type, msg)
        return __cb

    def _print_token_usage(self, usage):
        formatted_usage = ', '.join(f'{k}={v}' for k, v in usage.items())
        self._sys_output_callback(SYS_OUTPUT_TYPE.debug, f"Tokens Usage: ({formatted_usage})")

    def _append_dev_repair(self):
        if self._code_repaired == True:
            self.test_res += f"\n\n开发者的代码：\n{self.code}"
            self._code_repaired = False
    
    def _tester_reporting(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试报告生成中")
        
        usage = self._tester.send(prompt,
                                                  on_think=self._cb_ai(AI_OUTPUT_TYPE.tester_think),
                                                  on_resp=self._cb_ai(AI_OUTPUT_TYPE.tester_resp))

        self.report = self._tester.history[-1]["content"]
        self._print_token_usage(usage)
        
        if "<test_error>" in self.report.lower():
            self.test_code = extract_code(self.report)
            save("test_solution.py", self.test_code)
            
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本有错，已修复")
            self._stage = INTERNAL_STAGE.need_testing
            self._event_callback(EVENT_CODE.test_developing_done, self) 
        else:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试报告完成")
            self._stage = INTERNAL_STAGE.need_repairing
            self._event_callback(EVENT_CODE.reporting_done, self) 



    def _tester_developing(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本开发中")
        
        usage = self._tester.send(prompt,
                                                  on_think=self._cb_ai(AI_OUTPUT_TYPE.tester_think),
                                                  on_resp=self._cb_ai(AI_OUTPUT_TYPE.tester_resp))

        self.test_code = extract_code(self._tester.history[-1]["content"])
        save("test_solution.py", self.test_code)
        self._print_token_usage(usage)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本开发完成")
        self._stage = INTERNAL_STAGE.need_testing
        self._event_callback(EVENT_CODE.test_developing_done, self)


    def _repairing(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "修复中")
        
        usage = self._developer.send(prompt,
                                                     on_think=self._cb_ai(AI_OUTPUT_TYPE.developer_think),
                                                     on_resp=self._cb_ai(AI_OUTPUT_TYPE.developer_resp))

        output = self._developer.history[-1]["content"]
        if "<test_error>" in output.lower():
            raise DevelopConflict("开发者和测试工程师意见冲突")
        self.code = extract_code(output)
        save("solution.py", self.code)
        self._print_token_usage(usage)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "修复完成")
        self._stage = INTERNAL_STAGE.need_testing
        self._event_callback(EVENT_CODE.repairing_done, self)
        self._code_repaired = True


    def _developing(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "开发中")
        
        usage = self._developer.send(prompt,
                                                     on_think=self._cb_ai(AI_OUTPUT_TYPE.developer_think),
                                                     on_resp=self._cb_ai(AI_OUTPUT_TYPE.developer_resp))

        self.code = extract_code(self._developer.history[-1]["content"])
        save("solution.py", self.code)
        self._print_token_usage(usage)

        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "开发完成")
        self._stage = INTERNAL_STAGE.need_test_developing
        self._event_callback(EVENT_CODE.developing_done, self)


    def _analyzing(self):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "需求分析中")
        
        usage = self._analyst.send(self._requirement, on_think=self._cb_ai(AI_OUTPUT_TYPE.analyst_think),
                           on_resp=self._cb_ai(AI_OUTPUT_TYPE.analyst_resp))

        self.analysis = self._analyst.history[-1]["content"]
        self._print_token_usage(usage)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "分析完成")
        self._stage = INTERNAL_STAGE.need_developing
        self._event_callback(EVENT_CODE.analyzing_done, self)


    def _testing(self) -> bool:
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试运行中")
        
        resolver = DependencyResolver()
        try:
            resolver.install_from_files(["solution.py"])
        except SyntaxError as e:
            self.test_res = f"开发者代码（solution.py）语法错误：\n{e}"
            self._append_dev_repair()
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False
        except:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "无法补全依赖")
            pass
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "solution依赖已补全")

        try:
            resolver.install_from_files(["test_solution.py"])
        except SyntaxError as e:
            self.test_res = f"测试脚本（test_solution.py）语法错误：\n{e}"
            self._append_dev_repair()
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False
        except:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "无法补全依赖")
            pass
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "test_solution依赖已补全")

        try:
            res = subprocess.run([sys.executable, "test_solution.py"],
                                capture_output=True, text=True, timeout=120)
            time_out = False
            if res.returncode == 0:
                self.test_res = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
                self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试通过")
                self._event_callback(EVENT_CODE.done, self)
                return True
        except subprocess.TimeoutExpired as e:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试超时")
            time_out = True
            res = e

        if time_out:
            self.test_res = f"测试超时：\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        else:
            self.test_res = f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        self._append_dev_repair()
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
        self._stage = INTERNAL_STAGE.need_reporting
        self._event_callback(EVENT_CODE.testing_done, self)
        return False

