from __future__ import annotations
import sys, subprocess, weakref
from typing import Callable
from enum import Enum
from .api_session import *
from .utils import *
from .dependency_resolver import *

analyst_system_prompt=(
    "你是需求分析专家。\n"
    "用户会给出一个业务或算法需求，你需要：\n"
    "1. 提炼出清晰的功能描述和约束条件；\n"
    "2. 明确输入（stdin，或读取当前目录下的文件，注意格式、数据类型、边界条件）和输出（stdout，或写入当前目录下的文件）；\n"
    "3. 列出可能的异常情况及处理建议；\n"
    "4. 完整以自然语言输出项目需求要点，使用要点列表，需求不要太复杂，禁止编写代码；\n"
    "5. 开发者和测试工程师也是AI，你可以利用提示词工程的理论优化表述。\n"
    "开发者和测试工程师都只能使用python编写单文件代码，不能实现图形化，"
    "且不能有危险系统调用（修改系统配置，获得管理员权限，修改其他目录、文件等），"
    "如果用户需求不符合要求，直接输出\"<REFUSED>\"标志告诉我。\n"
    "注意你生成的需求分析里不要包含\"<REFUSED>\"标志，防止我误解你。"
)

developer_system_prompt=(
    "你是资深 Python 开发者。\n"
    "根据需求分析师提供的需求，要编写一个单文件Python脚本（我会帮你保存为solution.py）：\n"
    "1. 仅输出代码，不要有任何额外解释或注释之外的文字；\n"
    "2. 输入从stdin读取，输出写到stdout（输入可选，输出必须），也可以根据需求进行文件操作（仅限工作目录）；\n"
    "3. 如果需求有危险系统调用（修改系统配置，获得管理员权限，修改其他目录、文件等），务必输出\"<REFUSED>\"标志拒绝开发；\n"
    "4. 必要时可添加调试打印（stdout 或 stderr），由于测试工程师会进行黑盒测试，输出格式务必规范化；\n"
    "5. 要处理常见错误（空输入、格式错误、边界值）。\n"
    "如果测试工程师（也是AI）反馈错误，你将收到错误报告，需修复并重新输出完整代码。\n"
    "如果你认为测试工程师的测试不合理，输出\"<TEST_ERROR>\"标志告诉我。\n"
    "注意你生成的代码里不要包含这些标志，防止我误解你。"
)

tester_system_prompt=(
    "你是自动化测试工程师。\n"
    "第一次会话先根据需求分析及开发者代码（solution.py），生成一个 Python 测试脚本，要求：\n"
    "1. 只输出一个Python代码块，我会帮你保存为test_solution.py（和solution.py在同目录下）；\n"
    "2. 调用开发者脚本：python3 solution.py即可，不要有额外操作，输入通过stdin，输出通过stdout或stderr；\n"
    "3. 如果开发者代码中有文件操作，你也可以添加相关测试，一切文件操作仅限工作目录；\n"
    "4. 覆盖典型用例与边界场景，使用容错匹配以增强鲁棒性（例如去除多余空白）；\n"
    "5. 对每个测试用例打印调试信息，若全部通过调用sys.exit(0)，否则sys.exit(1)；\n"
    "6. 针对超时（60s）或异常情况捕获并报告。\n"
    "在下一次会话我会把测试脚本运行结果发给你，你有两种选择：\n"
    "1. 如果测试脚本（test_solution.py）本身有错误，或者你想修改测试脚本，务必先输出\"<TEST_ERROR>\"标志，然后紧跟新的测试脚本；\n"
    "2. 如果你确认开发者代码（solution.py）有问题，就给出错误分析和修改建议（可以携带测试脚本和测试结果的片段），但一定不要帮他写代码。\n"
    "注意：测试不要过于苛刻（只要没有逻辑问题，尽量让它通过），不要写无关文字，不允许存在多个代码块。\n"
    "警告：如果代码有危险系统调用（修改系统配置，获得管理员权限，修改其他目录、文件等），务必输出\"<REFUSED>\"标志拒绝测试。\n"
    "注意你生成的代码里不要包含这些标志，防止我误解你。\n"
    "写测试脚本/生成报告的流程会重复多次直到成功。"
)

class DevelopConflict(Exception):
    pass

class DevelopRefused(Exception):
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
        self._stop = False
        
        self._analyst.set_sys_prompt(analyst_system_prompt)
        self._developer.set_sys_prompt(developer_system_prompt)
        self._tester.set_sys_prompt(tester_system_prompt)
        
        self._analyst_ref = weakref.ref(self._analyst)
        self._developer_ref = weakref.ref(self._developer)
        self._tester_ref = weakref.ref(self._tester)

        
    
    def get_stage(self):
        return self._stage

    
    def stop(self):
        if self._stop: return
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "正在终止操作")
        self._stop = True
        if self._analyst_ref is not None: self._analyst.stop()
        if self._developer_ref is not None: self._developer.stop()
        if self._tester_ref is not None: self._tester.stop()


    def step(self) -> bool:
        if self._stop:
            return True

        if self._stage == INTERNAL_STAGE.need_analyzing:
            self._analyzing()
        elif self._stage == INTERNAL_STAGE.need_developing:
            self._developing(f"需求描述：\n{self.analysis}")
        elif self._stage == INTERNAL_STAGE.need_test_developing:
            self._tester_developing(f"需求描述：\n{self.analysis}\n\n\n开发者代码：\n{self.code}")
        elif self._stage == INTERNAL_STAGE.need_testing:
            res = self._testing()
            return res or self._stop
        elif self._stage == INTERNAL_STAGE.need_reporting:
            if self._code_repaired == True:
                self._tester_reporting(f"开发者修改后的代码：\n{self.code}\n\n\n运行结果：\n{self.test_res}\n如果你想修改测试脚本，别忘输出\"<TEST_ERROR>\"")
                self._code_repaired = False
            else:
                self._tester_reporting(f"运行结果：\n{self.test_res}\n如果你想修改测试脚本，别忘输出\"<TEST_ERROR>\"")
        elif self._stage == INTERNAL_STAGE.need_repairing:
            self._repairing(f"错误报告：\n{self.report}")

        return self._stop
            

    def _cb_ai(self, msg_type):
        def __cb(msg):
            self._ai_output_calllback(msg_type, msg)
        return __cb


    def _print_token_usage(self, usage):
        formatted_usage = ', '.join(f'{k}={v}' for k, v in usage.items())
        self._sys_output_callback(SYS_OUTPUT_TYPE.debug, f"Tokens Usage: ({formatted_usage})")

    
    def _tester_reporting(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试报告生成中")
        
        if self._stop: return
        usage = self._tester.send(prompt,
                                                  on_think=self._cb_ai(AI_OUTPUT_TYPE.tester_think),
                                                  on_resp=self._cb_ai(AI_OUTPUT_TYPE.tester_resp))

        self.report = self._tester.history[-1]["content"]
        if "<refused>" in self.report.lower() or "<refuse>" in self.report.lower():
            raise DevelopRefused("报告生成被拒绝")

        self._print_token_usage(usage)
        
        if "<test_error>" in self.report.lower() or "<testerror>" in self.report.lower():
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
        
        if self._stop: return
        usage = self._tester.send(prompt,
                                                  on_think=self._cb_ai(AI_OUTPUT_TYPE.tester_think),
                                                  on_resp=self._cb_ai(AI_OUTPUT_TYPE.tester_resp))

        output = self._tester.history[-1]["content"]
        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("测试脚本开发被拒绝")

        self.test_code = extract_code(output)
        save("test_solution.py", self.test_code)
        self._print_token_usage(usage)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本开发完成")
        self._stage = INTERNAL_STAGE.need_testing
        self._event_callback(EVENT_CODE.test_developing_done, self)


    def _repairing(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "修复中")
        
        if self._stop: return
        usage = self._developer.send(prompt,
                                                     on_think=self._cb_ai(AI_OUTPUT_TYPE.developer_think),
                                                     on_resp=self._cb_ai(AI_OUTPUT_TYPE.developer_resp))

        output = self._developer.history[-1]["content"]
        if "<test_error>" in output.lower() or "<testerror>" in output.lower():
            raise DevelopConflict("开发者和测试工程师意见冲突")
        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("开发被拒绝")
        
        self.code = extract_code(output)
        save("solution.py", self.code)
        self._print_token_usage(usage)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "修复完成")
        self._stage = INTERNAL_STAGE.need_testing
        self._event_callback(EVENT_CODE.repairing_done, self)
        self._code_repaired = True


    def _developing(self, prompt):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "开发中")
        
        if self._stop: return
        usage = self._developer.send(prompt,
                                                     on_think=self._cb_ai(AI_OUTPUT_TYPE.developer_think),
                                                     on_resp=self._cb_ai(AI_OUTPUT_TYPE.developer_resp))

        output = self._developer.history[-1]["content"]
        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("开发被拒绝")

        self.code = extract_code(output)
        save("solution.py", self.code)
        self._print_token_usage(usage)

        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "开发完成")
        self._stage = INTERNAL_STAGE.need_test_developing
        self._event_callback(EVENT_CODE.developing_done, self)


    def _analyzing(self):
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "需求分析中")
        
        if self._stop: return
        usage = self._analyst.send(self._requirement, on_think=self._cb_ai(AI_OUTPUT_TYPE.analyst_think),
                           on_resp=self._cb_ai(AI_OUTPUT_TYPE.analyst_resp))

        self.analysis = self._analyst.history[-1]["content"]
        if "<refused>" in self.analysis.lower() or "<refuse>" in self.analysis.lower():
            raise DevelopRefused("需求分析被拒绝")

        self._print_token_usage(usage)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "分析完成")
        self._stage = INTERNAL_STAGE.need_developing
        self._event_callback(EVENT_CODE.analyzing_done, self)


    def _testing(self) -> bool:
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试运行中")
        
        if self._stop: return True
        try:
            check_syntax("solution.py")
        except SyntaxError as e:
            self.test_res = f"开发者代码（solution.py）语法错误：\n{e}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False

        try:
            check_syntax("test_solution.py")
        except SyntaxError as e:
            self.test_res = f"测试脚本（test_solution.py）语法错误：\n{e}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False
        
        resolver = DependencyResolver()
        try:
            resolver.install_from_files()
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "依赖已补全")
        except Exception as e:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "无法补全依赖")
            raise

        """
        try:
            resolver.install_from_files(["solution.py"])
        except SyntaxError as e:
            self.test_res = f"开发者代码（solution.py）语法错误：\n{e}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False
        except:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "无法为 solution.py 补全依赖")
            raise
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "solution.py 依赖已补全")

        try:
            resolver.install_from_files(["test_solution.py"])
        except SyntaxError as e:
            self.test_res = f"测试脚本（test_solution.py）语法错误：\n{e}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False
        except:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "无法为 test_solution.py 补全依赖")
            raise
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "test_solution.py 依赖已补全")
        """
        
        try:
            res = subprocess.run([sys.executable, "test_solution.py"],
                                capture_output=True, text=True, timeout=120)
            time_out = False
            if res.returncode == 0:
                self.test_res = f"[stdout]:\n{res.stdout}\n[stderr]:\n{res.stderr}"
                self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试通过")
                self._event_callback(EVENT_CODE.done, self)
                return True
        except subprocess.TimeoutExpired as e:
            time_out = True
            res = e

        if time_out:
            self.test_res = f"测试超时：\n[stdout]:\n{res.stdout}\n[stderr]:\n{res.stderr}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试超时")
        else:
            self.test_res = f"[stdout]:\n{res.stdout}\n[stderr]:\n{res.stderr}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
        
        self._stage = INTERNAL_STAGE.need_reporting
        self._event_callback(EVENT_CODE.testing_done, self)
        return False

