from __future__ import annotations
import sys, subprocess, weakref
from typing import Callable
from enum import Enum
from .api_session import *
from .utils import *
from .dependency_resolver import *

analyst_system_prompt=(
    "你是 Python 开发需求分析专家。\n"
    "用户会给出一个业务或算法需求，你有两种选择：\n"
    "1. 如果你想让用户补充需求细节，以便更好地分析，就向用户提问：\n"
    "  - 尽量一次问清楚所有问题，问答回合最多三次；\n"
    "  - 如果达到次数上限，用户仍没有解释清楚，也不再提问，其余的凭借自己理解。\n"
    "2. 如果需求本身足够明确或已经通过问答完善，就开始需求分析：\n"
    "  - 先输出“<ANALYSIS>”标志表明下面是分析内容（而不是提问），然后再输出分析正文；\n"
    "  - 提炼出清晰的功能描述和约束条件；\n"
    "  - 明确输入（stdin 或读取当前目录下的文件，注意格式、数据类型、边界条件）和输出（stdout 或写入当前目录下的文件）；\n"
    "  - 列出可能的异常情况及处理建议；\n"
    "  - 完整以自然语言描述，使用要点列表，需求不要太复杂，禁止编写代码；\n"
    "  - 开发者和测试工程师也是AI，不要对他们要求过高，同时你可以用提示词工程的理论优化需求描述。\n"
    "特别注意：\n"
    "  - 开发者和测试工程师都只能使用 Python 编写单文件代码，不能实现图形化，且不能有危险调用（修改系统配置，获得管理员权限，操作其他目录、文件等），如果用户需求不符合要求，直接输出“<REFUSED>”标志拒绝分析！\n"
    "  - 只要你想正式开始分析（无论是否经过提问环节），必须输出“<ANALYSIS>”标志之后再输出分析正文！\n"
    "  - 需求分析正文不要有“<REFUSED>”和“<ANALYSIS>”及类似字样，这些标志只能出现在开头以避免误解！"
)

developer_system_prompt=(
    "你是资深 Python 开发者。\n"
    "根据需求分析师提供的需求，编写一个单文件 Python 脚本，我会帮你保存为“solution.py”，你要：\n"
    "  - 仅输出代码，不要有额外解释（但为了便于理解，代码内部要添加必要注释）；\n"
    "  - 输入从 stdin 读取，输出到 stdout （输入可选，输出必须），也可以根据需求进行文件操作（仅限当前工作目录）；\n"
    "  - 必要时添加调试输出，由于测试工程师进行黑盒测试（就像 Online Judge 一样），输出格式务必规范化；\n"
    "  - 要处理常见错误（空输入、格式错误、边界值）；\n"
    "  - 可以使用第三方库（你不用考虑依赖问题）；\n"
    "  - 要能直接通过“python solution.py”调用，不能在后台运行（避免影响测试）。\n"
    "特别注意：\n"
    "  - 如果开发需求有危险调用（修改系统配置，获得管理员权限，操作其他目录、文件等），直接输出“<REFUSED>”标志拒绝开发！\n"
    "  - 如果测试工程师（也是AI）给出错误报告，需修复并重新输出完整代码！\n"
    "  - 如果你认为测试不合理，坚持认为代码没问题，务必输出“<TEST_ERROR>”标志告诉我！\n"
    "  - 代码正文不要有“<REFUSED>”和“<TEST_ERROR>”及类似字样，这些标志只能出现在开头以避免误解！"
)

tester_system_prompt=(
    "你是 Python 自动化测试工程师。\n"
    "1. 第一次会话先根据需求描述及开发者代码 (solution.py) ，生成一个 Python 测试脚本 (test_solution.py) ，要求：\n"
    "  - 直接用“python solution.py”调用开发者代码，输入通过 (stdin) ，输出通过 stdout 或 stderr ；\n"
    "  - 如果开发者代码有文件操作，你也要添加相关测试，文件操作仅限当前工作目录；\n"
    "  - 覆盖典型用例与边界场景，使用容错匹配以增强鲁棒性（例如去除多余空白）；\n"
    "  - 对每个测试用例打印调试信息，便于后期生成报告，若全部通过调用 sys.exit(0) ，否则 sys.exit(1) ；\n"
    "  - 针对超时（60秒）或异常情况捕获并输出；\n"
    "  - 你生成的脚本必须只含一个 Python 代码块（我帮你保存为“test_solution.py”并安装依赖），要能直接通过“python test_solution.py”运行；\n"
    "  - 即使开发者代码 (solution.py) 有明显错误，也先完成测试脚本 (test_solution.py) ，通过测试体现错误；\n"
    "  - 测试不要太苛刻，可以跳过开发者难以处理的细节；\n"
    "  - 你的生成内容不要有无关文字，禁止存在多个代码块！\n"
    "2. 下一次会话我会给你测试脚本运行结果，你有两种选择：\n"
    "  - 如果测试脚本 (test_solution.py) 本身有问题，你想修改测试脚本，或只是想重新运行测试，务必先输出“<TEST_ERROR>”标志，然后紧跟新的测试脚本；\n"
    "  - 如果你确认开发者代码 (solution.py) 有问题，就给出错误报告和修改建议（可携带测试结果），但不要帮他写代码，他会自己修改。\n"
    "3. 特别注意：\n"
    "  - 如果开发者代码有危险调用（修改系统配置，获得管理员权限，操作其他目录、文件等），直接输出“<REFUSED>”标志拒绝测试！\n"
    "  - 要仔细分析开发者代码和运行结果，判断错误根源，先保证测试脚本本身合理！\n"
    "  - 上述“编写-测试-报告”会话流程将重复多次。只有测试脚本返回0，我才认为测试通过并终止会话，所以要保证测试脚本有正确的返回值！\n"
    "  - 测试脚本和错误报告正文不要有“<TEST_ERROR>”和“<REFUSED>”及类似字样，这些标志只能出现在开头以避免误解！"
)

add_on_analyst="（别忘你作为需求分析专家的要求：如果想正式开始分析，先输出“<ANALYSIS>”标志之后再给出分析正文）"
add_on_tester="（别忘你作为测试工程师的要求：如果想修改测试脚本后重新运行测试，就先输出“<TEST_ERROR>”标志然后务必给出新的测试脚本；如果想让开发者修改代码，就直接生成错误报告和修改建议）"

class DevelopConflict(Exception):
    pass


class DevelopRefused(Exception):
    pass


class DependencyError(Exception):
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
    question_done = 1
    analyzing_done = 2
    developing_done = 3
    test_developing_done = 4
    testing_done = 5
    reporting_done = 6
    repairing_done = 7


class INTERNAL_STAGE(Enum):
    need_analyzing = 0
    need_developing = 1
    need_test_developing = 2
    need_testing = 3
    need_reporting = 4
    need_repairing = 5


class CodingManager:
    def __init__(self,
                 analyst: OpenAISession,
                 developer: OpenAISession,
                 tester: OpenAISession,
                 ai_output_callback: Callable[[AI_OUTPUT_TYPE, str], None],
                 sys_output_callback: Callable[[SYS_OUTPUT_TYPE, str], None],
                 event_callback: Callable[[EVENT_CODE, CodingManager], None]
                 ):
        self._analyst = analyst
        self._developer = developer
        self._tester = tester
        self._ai_output_calllback = ai_output_callback
        self._sys_output_callback = sys_output_callback
        self._event_callback = event_callback
        
        self._stage = INTERNAL_STAGE.need_analyzing
        self.question = ""
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

    
    def chat(self, user_input: str) -> bool:
        if self._stop: return True

        if self._stage != INTERNAL_STAGE.need_analyzing:
            raise RuntimeError("重复的需求分析")
        
        res = self._analyzing(user_input + "\n" + add_on_analyst)
        return res or self._stop


    def step(self) -> bool:
        if self._stop: return True

        if self._stage == INTERNAL_STAGE.need_analyzing or self.analysis == "":
            raise RuntimeError("未完成需求分析")

        elif self._stage == INTERNAL_STAGE.need_developing:
            self._developing(f"需求描述：\n{self.analysis}")
        elif self._stage == INTERNAL_STAGE.need_test_developing:
            self._tester_developing(f"需求描述：\n{self.analysis}\n\n\n开发者代码：\n{self.code}")
        elif self._stage == INTERNAL_STAGE.need_testing:
            res = self._testing()
            return res or self._stop
        elif self._stage == INTERNAL_STAGE.need_reporting:
            if self._code_repaired == True:
                self._tester_reporting(f"开发者修改后的代码：\n{self.code}\n\n\n运行结果：\n{self.test_res}\n" + add_on_tester)
                self._code_repaired = False
            else:
                self._tester_reporting(f"运行结果：\n{self.test_res}\n" + add_on_tester)
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
        if self._stop: return
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试报告生成中")
        usage = self._tester.send(prompt,
                                                  on_think=self._cb_ai(AI_OUTPUT_TYPE.tester_think),
                                                  on_resp=self._cb_ai(AI_OUTPUT_TYPE.tester_resp))
        self.report = self._tester.history[-1]["content"]
        self._print_token_usage(usage)
        
        if "<refused>" in self.report.lower() or "<refuse>" in self.report.lower():
            raise DevelopRefused("报告生成被拒绝")
        
        if "<test_error>" in self.report.lower() or "<testerror>" in self.report.lower():
            self.test_code = extract_code(self.report).replace("<TEST_ERROR>", "", 1).lstrip()
            save("test_solution.py", self.test_code)
            
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本有错，已修复")
            self._stage = INTERNAL_STAGE.need_testing
            self._event_callback(EVENT_CODE.test_developing_done, self) 
        else:
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试报告完成")
            self._stage = INTERNAL_STAGE.need_repairing
            self._event_callback(EVENT_CODE.reporting_done, self) 


    def _tester_developing(self, prompt):
        if self._stop: return
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本开发中")
        usage = self._tester.send(prompt,
                                                  on_think=self._cb_ai(AI_OUTPUT_TYPE.tester_think),
                                                  on_resp=self._cb_ai(AI_OUTPUT_TYPE.tester_resp))
        output = self._tester.history[-1]["content"]
        self._print_token_usage(usage)

        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("测试脚本开发被拒绝")

        self.test_code = extract_code(output)
        save("test_solution.py", self.test_code)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试脚本开发完成")
        self._stage = INTERNAL_STAGE.need_testing
        self._event_callback(EVENT_CODE.test_developing_done, self)


    def _repairing(self, prompt):
        if self._stop: return

        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "修复中") 
        usage = self._developer.send(prompt,
                                                     on_think=self._cb_ai(AI_OUTPUT_TYPE.developer_think),
                                                     on_resp=self._cb_ai(AI_OUTPUT_TYPE.developer_resp))
        output = self._developer.history[-1]["content"]
        self._print_token_usage(usage)
        
        if "<test_error>" in output.lower() or "<testerror>" in output.lower():
            raise DevelopConflict("开发者和测试工程师意见冲突")
        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("开发被拒绝")
        
        self.code = extract_code(output)
        save("solution.py", self.code)
        
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "修复完成")
        self._stage = INTERNAL_STAGE.need_testing
        self._event_callback(EVENT_CODE.repairing_done, self)
        self._code_repaired = True


    def _developing(self, prompt):
        if self._stop: return

        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "开发中")
        usage = self._developer.send(prompt,
                                                     on_think=self._cb_ai(AI_OUTPUT_TYPE.developer_think),
                                                     on_resp=self._cb_ai(AI_OUTPUT_TYPE.developer_resp))
        output = self._developer.history[-1]["content"]
        self._print_token_usage(usage)
        
        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("开发被拒绝")

        self.code = extract_code(output)
        save("solution.py", self.code)

        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "开发完成")
        self._stage = INTERNAL_STAGE.need_test_developing
        self._event_callback(EVENT_CODE.developing_done, self)


    def _analyzing(self, requirement) -> bool:
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "需求分析中")
        
        if self._stop: return True
        usage = self._analyst.send(requirement, on_think=self._cb_ai(AI_OUTPUT_TYPE.analyst_think),
                           on_resp=self._cb_ai(AI_OUTPUT_TYPE.analyst_resp))

        output = self._analyst.history[-1]["content"]
        self._print_token_usage(usage)
        
        if "<refused>" in output.lower() or "<refuse>" in output.lower():
            raise DevelopRefused("需求分析被拒绝")

        if "<analysis>" in output.lower() or "<analyses>"  in output.lower():
            self.analysis = output.replace("<ANALYSIS>", "", 1).lstrip()
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "分析完成")
            self._stage = INTERNAL_STAGE.need_developing
            self._event_callback(EVENT_CODE.analyzing_done, self)
            return True
        else:
            self.question = output
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "需要补充信息")
            self._event_callback(EVENT_CODE.question_done, self)
            return False


    def _testing(self) -> bool:
        self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试运行中")
        
        if self._stop: return True
        try:
            check_syntax("solution.py")
        except SyntaxError as e:
            self.test_res = f"开发者代码 (solution.py) 语法错误：\n{e}"
            self._sys_output_callback(SYS_OUTPUT_TYPE.info, "测试未通过")
            self._stage = INTERNAL_STAGE.need_reporting
            self._event_callback(EVENT_CODE.testing_done, self)
            return False

        try:
            check_syntax("test_solution.py")
        except SyntaxError as e:
            self.test_res = f"测试脚本 (test_solution.py) 语法错误：\n{e}"
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
            raise DependencyError("无法补全依赖") from e

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

