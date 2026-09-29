# -*- coding: utf-8 -*-
"""Anti-antipaste 核心引擎：模拟键盘逐字输入，支持暂停/继续/从头开始/自动暂停。"""
import random
import threading
import time

from pynput.keyboard import Controller, Key, Listener as KeyListener
from pynput.mouse import Listener as MouseListener

try:
    import ctypes
    _user32 = ctypes.windll.user32
except Exception:
    _user32 = None


def foreground_window():
    """当前前台窗口句柄；不可用时返回 None。"""
    if _user32 is None:
        return None
    try:
        return _user32.GetForegroundWindow()
    except Exception:
        return None


class TyperEngine:
    """逐字符注入键盘事件的打字引擎。

    params 为共享字典，引擎每打一个字符都实时读取最新值，
    因此输入中（含暂停时）修改速度等参数立即生效。
    支持的键：interval_ms, jitter_pct, long_pause_pct, countdown_s,
              trailing_enter, check_focus, check_mouse, own_hwnd
    """

    def __init__(self):
        self.controller = Controller()
        self.stop_event = threading.Event()      # 完全终止
        self.pause_event = threading.Event()     # 置位=输入中，清零=已暂停
        self.restart_event = threading.Event()   # 请求重新进入倒计时并继续/重打
        self.thread = None
        self.index = 0
        self.total = 0
        self._reset_on_restart = False
        self._monitor_stop = threading.Event()
        self._mouse_listener = None
        self._cb = {}

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    @property
    def paused(self):
        return self.running and not self.pause_event.is_set()

    # ---- 外部控制 ----
    def start(self, text, params, on_status, on_progress, on_state):
        self.stop_event.clear()
        self.restart_event.clear()
        self.pause_event.set()
        self.index = 0
        self.total = len(text)
        self._cb = {"status": on_status, "progress": on_progress, "state": on_state}
        self.thread = threading.Thread(target=self._run, args=(text, params), daemon=True)
        self.thread.start()

    def pause(self, reason="手动暂停"):
        if not self.running or not self.pause_event.is_set():
            return
        self.pause_event.clear()
        cb = self._cb.get("state")
        if cb:
            cb("paused", reason)

    def resume(self):
        """从暂停位置继续（带倒计时）。"""
        if not self.running:
            return
        self._reset_on_restart = False
        self.restart_event.set()
        self.pause_event.set()

    def restart(self):
        """从头重新输入（带倒计时）。"""
        if not self.running:
            return
        self._reset_on_restart = True
        self.restart_event.set()
        self.pause_event.set()

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()  # 唤醒可能处于暂停等待的循环

    # ---- 内部 ----
    def _interruptible_sleep(self, seconds):
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return True
            if self.stop_event.is_set() or self.restart_event.is_set():
                return False
            time.sleep(min(0.05, remaining))

    def _wait_while_paused(self):
        """暂停期间阻塞；返回 False 表示收到停止或重启指令。"""
        while not self.pause_event.is_set():
            if self.stop_event.is_set() or self.restart_event.is_set():
                return False
            time.sleep(0.05)
        return True

    def _countdown(self, countdown_s):
        """返回 'ok' / 'stopped' / 'restart'。"""
        for remaining in range(int(countdown_s), 0, -1):
            if self.stop_event.is_set():
                return "stopped"
            if self.restart_event.is_set():
                return "restart"
            if not self._wait_while_paused():
                return "stopped" if self.stop_event.is_set() else "restart"
            self._cb["status"](f"倒计时 {remaining} 秒…请切换到目标输入框")
            if not self._interruptible_sleep(1.0):
                return "stopped" if self.stop_event.is_set() else "restart"
        return "ok"

    def _focus_monitor(self, hwnd0):
        """前台窗口轮询：一旦切换且正在输入，则自动暂停。"""
        while not self._monitor_stop.is_set() and not self.stop_event.is_set():
            if self.pause_event.is_set() and not self.restart_event.is_set():
                current = foreground_window()
                if hwnd0 is not None and current is not None and current != hwnd0:
                    self.pause("检测到前台窗口切换，已自动暂停")
                    return
            time.sleep(0.1)

    def _start_mouse_monitor(self, own_hwnd):
        def on_click(x, y, button, pressed):
            if not (pressed and self.pause_event.is_set()
                    and not self.restart_event.is_set()):
                return
            # 点击本工具自己的窗口（如暂停按钮）不触发自动暂停，
            # 否则会与按钮的暂停/继续逻辑打架
            if own_hwnd and foreground_window() == own_hwnd:
                return
            self.pause("检测到鼠标点击，已自动暂停")
        self._mouse_listener = MouseListener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _stop_monitors(self):
        self._monitor_stop.set()
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

    def _run(self, text, params):
        stopped = False
        try:
            while not self.stop_event.is_set():
                self.restart_event.clear()
                self.pause_event.set()
                if self._reset_on_restart:
                    self.index = 0
                    self._reset_on_restart = False
                self._cb["state"]("running", "")
                self._cb["progress"](self.index, self.total)

                result = self._countdown(params.get("countdown_s", 3))
                if result == "stopped":
                    stopped = True
                    break
                if result == "restart":
                    continue

                # 倒计时结束，开始本轮输入（监控开关按本轮开始时的参数）
                self._monitor_stop.clear()
                hwnd0 = foreground_window() if params.get("check_focus", True) else None
                if hwnd0 is not None:
                    threading.Thread(target=self._focus_monitor, args=(hwnd0,),
                                     daemon=True).start()
                if params.get("check_mouse", True):
                    self._start_mouse_monitor(params.get("own_hwnd"))

                self._cb["status"]("正在输入…（F8 暂停）")

                while self.index < self.total:
                    if self.stop_event.is_set():
                        stopped = True
                        break
                    if self.restart_event.is_set():
                        break
                    if not self._wait_while_paused():
                        break
                    if self.stop_event.is_set():
                        stopped = True
                        break
                    if self.restart_event.is_set():
                        break

                    ch = text[self.index]
                    try:
                        self.controller.type(ch)
                    except Exception:
                        pass  # 个别字符注入失败时跳过，不中断整体
                    self.index += 1
                    self._cb["progress"](self.index, self.total)

                    # 每个字符都读取最新参数：暂停时改速度，继续后立即生效
                    base = max(1, params.get("interval_ms", 15)) / 1000.0
                    j = max(0, params.get("jitter_pct", 35)) / 100.0
                    lp = max(0, min(50, params.get("long_pause_pct", 2))) / 100.0
                    delay = base * max(0.05, 1.0 + random.uniform(-j, j))
                    if lp > 0 and random.random() < lp:
                        delay += random.uniform(0.4, 1.2)  # 偶发"思考"长停顿
                    if not self._interruptible_sleep(delay):
                        break

                self._stop_monitors()

                if stopped:
                    break
                if self.restart_event.is_set():
                    continue  # 继续/重打：回到倒计时
                if self.index >= self.total:
                    if params.get("trailing_enter", False):
                        try:
                            self.controller.type("\n")
                        except Exception:
                            pass
                    break
                # 暂停状态下循环退出但未收到新指令：继续等待
                if not self.pause_event.is_set():
                    continue
                break
        finally:
            self._stop_monitors()
            self._cb["state"]("stopped" if stopped else "done", "")


class HotkeyListener:
    """全局 F8 热键：暂停 / 继续切换。"""

    def __init__(self, on_toggle):
        self._on_toggle = on_toggle
        self._listener = None

    def start(self):
        if self._listener is None:
            self._listener = KeyListener(on_press=self._on_press)
            self._listener.daemon = True
            self._listener.start()

    def _on_press(self, key):
        try:
            if key == Key.f8:
                self._on_toggle()
        except Exception:
            pass

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
