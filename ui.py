# -*- coding: utf-8 -*-
"""Anti-antipaste 界面：DPI 适配 + 现代扁平风。"""
import ctypes
import os
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from engine import HotkeyListener, TyperEngine

APP_TITLE = "Anti-antipaste"

# 界面配色
ACCENT = "#4F6BED"
ACCENT_DARK = "#3B53C4"
BG = "#F2F3F7"
TEXT = "#262830"
SUBTLE = "#6B7280"
BORDER = "#D6D9E0"

# 默认参数
DEFAULT_SETTINGS = {
    "interval": 15,
    "jitter": 35,
    "pause": 2,
    "countdown": 3,
    "trailing_enter": False,
    "topmost": True,
    "check_focus": True,
    "check_mouse": True,
}


def resource_path(name):
    """打包后从 _MEIPASS 读资源，开发时从脚本目录读。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def enable_dpi_awareness():
    """声明 DPI 感知，避免系统位图拉伸导致的字体模糊。需在创建窗口前调用。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # DPI 适配：让 tkinter 按物理像素渲染，字体清晰
        dpi = self.winfo_fpixels("1i")
        self._scale = dpi / 96.0
        self.tk.call("tk", "scaling", dpi / 72.0)
        s = self._scale
        self.title(APP_TITLE)
        self.geometry(f"{int(620 * s)}x{int(640 * s)}")
        self.minsize(int(560 * s), int(580 * s))

        self._settings = dict(DEFAULT_SETTINGS)
        self._live_params = {}  # 引擎实时读取的参数表

        self.engine = TyperEngine()
        self.hotkey = HotkeyListener(self._on_hotkey_toggle)
        self.hotkey.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_style()
        self._build_ui()
        self._bind_params_sync()
        self._sync_live_params()

    def _px(self, v):
        """按 DPI 缩放像素尺寸。"""
        return int(v * self._scale)

    def _setup_style(self):
        """现代扁平风主题。"""
        self.configure(bg=BG)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT,
                        font=("Microsoft YaHei UI", 9))
        style.configure("Section.TLabel", background=BG, foreground=TEXT,
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=ACCENT_DARK,
                        font=("Microsoft YaHei UI", 9))
        style.configure("Tip.TLabel", background=BG, foreground=SUBTLE,
                        font=("Microsoft YaHei UI", 8))
        style.configure("TLabelframe", background=BG, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG, foreground=TEXT,
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TSpinbox", fieldbackground="#FFFFFF", bordercolor=BORDER,
                        arrowcolor=SUBTLE, padding=2)
        style.configure("TButton", padding=(14, 7), font=("Microsoft YaHei UI", 9),
                        background="#FFFFFF", foreground=TEXT, bordercolor=BORDER)
        style.map("TButton",
                  background=[("disabled", "#E9EBF2"), ("active", "#E8EAF3")],
                  foreground=[("disabled", SUBTLE)])
        style.configure("Accent.TButton", padding=(16, 7),
                        font=("Microsoft YaHei UI", 9, "bold"),
                        background=ACCENT, foreground="#FFFFFF",
                        bordercolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("disabled", "#B9C0D8"), ("pressed", ACCENT_DARK),
                              ("active", ACCENT_DARK)],
                  foreground=[("disabled", "#F4F5FA")])
        style.configure("TProgressbar", troughcolor="#E4E6EE", background=ACCENT,
                        bordercolor="#E4E6EE", lightcolor=ACCENT,
                        darkcolor=ACCENT, thickness=self._px(10))

    def _build_ui(self):
        main = ttk.Frame(self, padding=self._px(12))
        main.pack(fill="both", expand=True)
        pad = {"padx": 2, "pady": self._px(4)}

        ttk.Label(main, text="要输入的内容（粘贴或键入到下面）：",
                  style="Section.TLabel").pack(anchor="w", **pad)
        self.text = scrolledtext.ScrolledText(
            main, height=10, wrap="word", undo=True,
            font=("Microsoft YaHei UI", 10), bg="#FFFFFF", fg=TEXT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT, padx=self._px(8), pady=self._px(6))
        self.text.pack(fill="both", expand=True, **pad)

        # 参数区
        opts = ttk.LabelFrame(main, text="输入节奏（修改后实时生效）",
                              padding=self._px(6))
        opts.pack(fill="x", **pad)

        s = self._settings
        self.interval_var = tk.IntVar(value=int(s["interval"]))
        self.jitter_var = tk.IntVar(value=int(s["jitter"]))
        self.pause_var = tk.IntVar(value=int(s["pause"]))
        self.countdown_var = tk.IntVar(value=int(s["countdown"]))
        self.enter_var = tk.BooleanVar(value=bool(s["trailing_enter"]))

        # 数字输入框：只允许键入数字，焦点离开时为空则回退默认值
        digit_vcmd = (self.register(lambda p: p == "" or p.isdigit()), "%P")

        def make_spin(parent, var, lo, hi, step, default):
            spin = ttk.Spinbox(parent, from_=lo, to=hi, increment=step, width=7,
                               textvariable=var, validate="key",
                               validatecommand=digit_vcmd)
            spin.bind("<FocusOut>", lambda e, v=var, d=default, a=lo, b=hi:
                      self._on_spin_focusout(v, d, a, b))
            return spin

        row1 = ttk.Frame(opts)
        row1.pack(fill="x", padx=self._px(8), pady=self._px(4))
        ttk.Label(row1, text="字符间隔(ms):").pack(side="left")
        make_spin(row1, self.interval_var, 5, 2000, 5,
                  int(s["interval"])).pack(side="left", padx=(2, self._px(24)))
        ttk.Label(row1, text="随机浮动(%):").pack(side="left")
        make_spin(row1, self.jitter_var, 0, 100, 5,
                  int(s["jitter"])).pack(side="left", padx=(2, 0))

        row2 = ttk.Frame(opts)
        row2.pack(fill="x", padx=self._px(8), pady=self._px(4))
        ttk.Label(row2, text="长停顿概率(%):").pack(side="left")
        make_spin(row2, self.pause_var, 0, 50, 1,
                  int(s["pause"])).pack(side="left", padx=(2, self._px(24)))
        ttk.Label(row2, text="启动倒计时(秒):").pack(side="left")
        make_spin(row2, self.countdown_var, 0, 15, 1,
                  int(s["countdown"])).pack(side="left", padx=(2, 0))

        row3 = ttk.Frame(opts)
        row3.pack(fill="x", padx=self._px(8), pady=self._px(4))
        ttk.Checkbutton(row3, text="输入完成后自动回车",
                        variable=self.enter_var).pack(side="left")

        # 辅助功能区
        aux = ttk.LabelFrame(main, text="辅助功能", padding=self._px(6))
        aux.pack(fill="x", **pad)

        self.topmost_var = tk.BooleanVar(value=bool(s["topmost"]))
        self.check_focus_var = tk.BooleanVar(value=bool(s["check_focus"]))
        self.check_mouse_var = tk.BooleanVar(value=bool(s["check_mouse"]))

        self.attributes("-topmost", bool(s["topmost"]))
        ttk.Checkbutton(aux, text="窗口置顶", variable=self.topmost_var,
                        command=self._on_topmost_toggle).pack(
                            side="left", padx=self._px(8), pady=self._px(4))
        ttk.Checkbutton(aux, text="窗口切换时自动暂停",
                        variable=self.check_focus_var).pack(
                            side="left", padx=self._px(8), pady=self._px(4))
        ttk.Checkbutton(aux, text="鼠标点击时自动暂停",
                        variable=self.check_mouse_var).pack(
                            side="left", padx=self._px(8), pady=self._px(4))

        # 按钮区
        btns = ttk.Frame(main)
        btns.pack(fill="x", pady=(self._px(10), self._px(4)))
        self.start_btn = ttk.Button(btns, text="开始输入", style="Accent.TButton",
                                    command=self._on_start)
        self.start_btn.pack(side="left")
        self.pause_btn = ttk.Button(btns, text="暂停 (F8)", command=self._on_pause_toggle,
                                    state="disabled")
        self.pause_btn.pack(side="left", padx=self._px(8))
        self.restart_btn = ttk.Button(btns, text="从头开始", command=self._on_restart,
                                      state="disabled")
        self.restart_btn.pack(side="left")
        ttk.Button(btns, text="清空内容",
                   command=self._on_clear).pack(side="left", padx=self._px(8))

        # 进度区
        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.pack(fill="x", pady=(self._px(8), self._px(4)))
        self.status_var = tk.StringVar(value="就绪。点击开始后，请在倒计时内切换到目标输入框。")
        ttk.Label(main, textvariable=self.status_var, style="Status.TLabel",
                  wraplength=self._px(560)).pack(anchor="w", **pad)

        tip = ("提示：模拟真实键盘输入，不走剪贴板，支持中文；"
               "F8 暂停/继续；速度等参数随时修改随时生效。")
        ttk.Label(main, text=tip, style="Tip.TLabel",
                  wraplength=self._px(560)).pack(anchor="w", **pad)

    # ---- 参数同步 ----
    def _bind_params_sync(self):
        """任一参数变化即同步到引擎实时参数表。"""
        for var in (self.interval_var, self.jitter_var, self.pause_var,
                    self.countdown_var, self.enter_var, self.topmost_var,
                    self.check_focus_var, self.check_mouse_var):
            var.trace_add("write", lambda *_: self._sync_live_params())

    def _on_spin_focusout(self, var, default, lo, hi):
        """数字框焦点离开：为空或非法则回退默认值，并夹在允许范围内。"""
        try:
            v = int(var.get())
        except Exception:
            v = default
        var.set(max(lo, min(hi, v)))

    def _sync_live_params(self):
        """把界面参数同步到引擎共享参数表，引擎逐字符实时读取。"""
        try:
            self._live_params.update({
                "interval_ms": int(self.interval_var.get()),
                "jitter_pct": int(self.jitter_var.get()),
                "long_pause_pct": int(self.pause_var.get()),
                "countdown_s": int(self.countdown_var.get()),
                "trailing_enter": bool(self.enter_var.get()),
                "check_focus": bool(self.check_focus_var.get()),
                "check_mouse": bool(self.check_mouse_var.get()),
                "own_hwnd": self.winfo_id(),
            })
        except Exception:
            pass  # 输入途中变量暂时为空等非法值时忽略

    # ---- 事件 ----
    def _on_topmost_toggle(self):
        self.attributes("-topmost", bool(self.topmost_var.get()))

    def _on_clear(self):
        """清空内容：同时终止当前输入会话并把按钮状态重置为初始。"""
        if self.engine.running:
            self.engine.stop()
        self.text.delete("1.0", "end")
        self.progress.config(value=0)
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="暂停 (F8)")
        self.restart_btn.config(state="disabled")
        self.status_var.set("就绪。点击开始后，请在倒计时内切换到目标输入框。")

    def _on_start(self):
        if self.engine.running:
            return
        content = self.text.get("1.0", "end-1c")
        if not content:
            messagebox.showwarning(APP_TITLE, "请先输入或粘贴要模拟输入的内容。")
            return
        try:
            self._sync_live_params()
            int(self.interval_var.get())
        except Exception:
            messagebox.showerror(APP_TITLE, "参数格式不正确，请检查数字输入。")
            return

        self.progress.config(maximum=max(1, len(content)), value=0)
        self.engine.start(
            text=content,
            params=self._live_params,
            on_status=lambda s: self.after(0, self.status_var.set, s),
            on_progress=lambda d, t: self.after(0, self._update_progress, d, t),
            on_state=lambda st, r: self.after(0, self._on_state, st, r),
        )

    def _update_progress(self, done, total):
        self.progress.config(maximum=max(1, total), value=done)
        if self.engine.paused:
            self.status_var.set(f"已暂停于 {done}/{total}")
        else:
            self.status_var.set(f"正在输入… {done}/{total}（F8 暂停）")

    def _on_pause_toggle(self):
        if not self.engine.running:
            return
        if self.engine.paused:
            self.engine.resume()
        else:
            self.engine.pause("手动暂停")

    def _on_hotkey_toggle(self):
        if self.engine.running:
            self.after(0, self._on_pause_toggle)

    def _on_restart(self):
        if self.engine.running:
            self.engine.restart()

    def _on_state(self, state, reason):
        if state == "running":
            self.start_btn.config(state="disabled")
            self.pause_btn.config(state="normal", text="暂停 (F8)")
            self.restart_btn.config(state="normal")
        elif state == "paused":
            self.pause_btn.config(state="normal", text="继续 (F8)")
            self.restart_btn.config(state="normal")
            self.status_var.set(f"{reason}（{self.engine.index}/{self.engine.total}）"
                                f"可继续或从头开始，速度等参数可随时调整。")
        else:  # done / stopped
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled", text="暂停 (F8)")
            self.restart_btn.config(state="disabled")
            if state == "done":
                self.progress.config(value=self.progress["maximum"])
                self.status_var.set("输入完成 ✔")
            else:
                self.status_var.set("已停止。")

    def _on_close(self):
        self.engine.stop()
        self.hotkey.stop()
        self.destroy()
