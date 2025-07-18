import sys, os, shutil, threading
from collections import deque
import tkinter as tk
import tkinter.font as tkfont
from tkinter.scrolledtext import ScrolledText
from pkg.coding_manager import *
from pkg.utils import *

ROOT_SCALING = 1.5 
FONT_FAMILY  = "Noto Sans CJK SC" 
FONT_SIZE    = 8 
COLOR_GOLD   = "#DAA520"

manager = None
stopped = False
input_event = threading.Event()      
step_event = threading.Event()      
lock= threading.Lock()               
pending_updates = deque()
shared_input = ""                        

def stop_func():
    global stopped
    global manager
    if stopped: return
    stopped = True
    if manager is not None:
        manager.stop()
    input_event.set()
    step_event.set()
    

class ChatUI:
    POLL_MS = 20     # 刷新周期：20 ms ≈ 50 FPS

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AI Development")
        self.root.tk.call('tk', 'scaling', ROOT_SCALING)

        # 修改全局默认字体
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family=FONT_FAMILY, size=FONT_SIZE)

        self.text_map = {} 
        self._build_layout()
        self._poll_updates()         # 开启 UI 轮询

    # -- 构造布局 --
    def _build_layout(self):
        #cfg = dict(width=62, height=8, wrap=tk.WORD)
        cfg = dict(width=120, height=7,
                   wrap=tk.WORD,
                   font=(FONT_FAMILY,FONT_SIZE),
                   spacing1=1, spacing2=4, spacing3=1)

        def block(row: int, title: str, key: str): #初始化文本框
            tk.Label(self.root, text=title).grid(row=row, column=0, sticky="w")
            text = ScrolledText(self.root, **cfg)
            text.grid(row=row+1, column=0, columnspan=4, padx=2, pady=2)
            self.text_map[key] = text
            tk.Button(self.root, text="清屏", width=6,
                      command=lambda k=key: self._clear(k)).grid(row=row, column=3, sticky="e")

        block(0, "Analyst", "chat1")
        block(2, "Developer", "chat2")
        block(4, "Tester", "chat3")
        block(6, "System Info", "sys1")
        block(8, "Error", "sys2")

        # 初始化：输入框 & 按钮
        #self.entry = tk.Entry(self.root, width=52)
        #self.entry.grid(row=10, column=0, padx=2, pady=4, sticky="w")
        #self.entry.bind("<Return>", self._send)
        tk.Label(self.root, text="User Input").grid(row=10, column=0, sticky="w")
        self.input_box = ScrolledText(
            self.root,
            width=120, height=4,
            wrap=tk.WORD,
            spacing1=1, spacing2=4, spacing3=1,
            font=(FONT_FAMILY, FONT_SIZE)
        )
        self.input_box.grid(row=11, column=0, columnspan=4, padx=4, pady=4)
        self.input_box.bind("<Return>", self._send())

        tk.Button(self.root, text="发送", command=self._send).grid(row=14, column=0, sticky="w")
        tk.Button(self.root, text="下一步",
                  command=step_event.set).grid(row=14, column=1)
        tk.Button(self.root, text="复位",
                  command=stop_func).grid(row=14, column=2)

    # -- 发送按钮 --
    def _send(self, *_):
        global shared_input
        msg = self.input_box.get(1.0, tk.END).strip()
        if msg:
            shared_input = msg
            input_event.set()
        self.input_box.delete(1.0, tk.END)

    # -- 清屏按钮 --
    def _clear(self, key: str):
        self.text_map[key].delete("1.0", tk.END)

    # -- 向窗口追加字符（仅主线程调用） --


    def _append(self, key: str, char: str, color: str):
        widget: tk.Text = self.text_map[key]
        tag = f"clr_{color}"
        if tag not in widget.tag_names():
            widget.tag_config(tag, foreground=color)
        widget.insert(tk.END, char, (tag,))
        widget.see(tk.END)
    
    def _poll_updates(self):
        batch = []
        with lock:
            while pending_updates:
                batch.append(pending_updates.popleft())
    
        for win, ch, color in batch:
            self._append(win, ch, color)
    
        self.root.after(self.POLL_MS, self._poll_updates)
    

def sys_printer(msg_type, msg):
    with lock:
        if msg_type == SYS_OUTPUT_TYPE.debug:
            pending_updates.extend(("sys1", ch, COLOR_GOLD) for ch in msg + '\n')
        else:
            pending_updates.extend(("sys1", ch, "red") for ch in msg + '\n')


def ai_printer(msg_type, msg):
    with lock: 
        if msg_type == AI_OUTPUT_TYPE.analyst_resp:
            pending_updates.extend(("chat1", ch, "green") for ch in msg)
        elif msg_type == AI_OUTPUT_TYPE.analyst_think:
            pending_updates.extend(("chat1", ch, COLOR_GOLD) for ch in msg)
        elif msg_type == AI_OUTPUT_TYPE.developer_resp:
            pending_updates.extend(("chat2", ch, "green") for ch in msg)
        elif msg_type == AI_OUTPUT_TYPE.developer_think:
            pending_updates.extend(("chat2", ch, COLOR_GOLD) for ch in msg)
        elif msg_type == AI_OUTPUT_TYPE.tester_resp:
            pending_updates.extend(("chat3", ch, "green") for ch in msg)
        elif msg_type == AI_OUTPUT_TYPE.tester_think:
            pending_updates.extend(("chat3", ch, COLOR_GOLD) for ch in msg)


def event_callback(event, manager):
    with lock:
        if event == EVENT_CODE.question_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "问题如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.question + '\n')
        elif event == EVENT_CODE.analyzing_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "分析如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.analysis + '\n')
        elif event == EVENT_CODE.developing_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "代码如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.code + '\n')
        elif event == EVENT_CODE.test_developing_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "测试代码如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.test_code + '\n')
        elif event == EVENT_CODE.testing_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "测试结果如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.test_res + '\n')
        elif event == EVENT_CODE.reporting_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "报告如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.report + '\n')
        elif event == EVENT_CODE.repairing_done:
            pending_updates.extend(("sys1", ch, "red") for ch in "修复如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.code + '\n')
        elif event == EVENT_CODE.done:
            pending_updates.extend(("sys1", ch, "red") for ch in "测试结果如下\n")
            pending_updates.extend(("sys1", ch, "green") for ch in manager.test_res + '\n')
            pending_updates.extend(("sys1", ch, "red") for ch in "开发完成！\n")
            

def error_printer(msg: str):
    with lock:
        pending_updates.extend(("sys2", ch, "red") for ch in msg + '\n')
    

def ai_worker():
    token = os.getenv("API_KEY") 
    if not token:
        print("API_KEY 未设置")
        sys.exit(1)

    del_path = Path("debug_payloads")
    shutil.rmtree(del_path, ignore_errors=True)
    model_analyst = "deepseek-v3"
    model_developer = "deepseek-v3"
    model_tester = "deepseek-v3"
    
    while True:
        global stopped
        global manager
        input_event.clear()
        step_event.clear()
        stopped = False
        analyst = OpenAISession(
            base_url="https://api.lkeap.cloud.tencent.com/v1",
            api_key=token,
            model=model_analyst,
            extra_params={"temperature": 0.4}
        )
        developer = OpenAISession(
            base_url="https://api.lkeap.cloud.tencent.com/v1",
            api_key=token,
            model=model_developer,
            extra_params={"temperature": 0.4}
        )
        tester = OpenAISession(
            base_url="https://api.lkeap.cloud.tencent.com/v1",
            api_key=token,
            model=model_tester,
            extra_params={"temperature": 0.4}
        )
        manager = CodingManager(analyst=analyst, developer=developer, tester=tester,
                                sys_output_callback=sys_printer, ai_output_callback=ai_printer, event_callback=event_callback)
        

        while not stopped:
            if input_event.set() and stopped: break
            input_event.clear()
            input_event.wait()
            input_event.clear()
            if stopped: break
            try:
                if manager.chat(user_input=shared_input): break 
            except GenerationInterrupted:
                error_printer("生成终止")
                stopped = True
                break
            except Exception as e:
                error_printer(str(e))
                stopped = True
                break

        if stopped:
            continue

        while not stopped:
            if step_event.set() and stopped: break
            step_event.clear()
            step_event.wait()
            step_event.clear()
            if stopped: break
            try:
                if manager.step(): break 
            except DependencyError:
                error_printer("异常处理失败，请手动处理后继续")
            except DevelopConflict:
                error_printer("开发者和测试工程师意见冲突")
                stopped = True
                break
            except GenerationInterrupted:
                error_printer("生成终止")
                stopped = True
                break
            except Exception as e:
                error_printer(str(e))
                stopped = True
                break
                

if __name__ == "__main__":
    threading.Thread(target=ai_worker, daemon=True).start()
    ChatUI(tk.Tk()).root.mainloop()

