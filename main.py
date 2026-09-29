# -*- coding: utf-8 -*-
"""
Anti-antipaste - 模拟键盘逐字输入小工具
用途：把文本内容以"真人打字"的方式输入到禁止粘贴的输入框中。
特性：
  - 字符间隔可调（毫秒），默认 15ms
  - 随机延迟抖动 + 偶发长停顿（模拟真人打字节奏，防检测）
  - 启动倒计时（留出时间切换到目标窗口）
  - 窗口置顶
  - 自动暂停：检测到前台窗口切换 / 鼠标点击时自动暂停
  - 暂停后可从断点继续，也可从头重新输入
  - 速度等参数修改后实时生效（包括暂停时修改，继续即用新参数）
  - F8 全局热键：暂停 / 继续
  - 支持中文等 Unicode 字符（直接以键盘事件注入，不经过剪贴板）

代码结构：
  engine.py  打字引擎与全局热键
  ui.py      界面（DPI 适配 + 样式）
  main.py    入口与自检
"""
import argparse
import sys
import time

from engine import TyperEngine
from ui import APP_TITLE, App, DEFAULT_SETTINGS, enable_dpi_awareness


def _wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _params(**overrides):
    p = {"interval_ms": 15, "jitter_pct": 35, "long_pause_pct": 2,
         "countdown_s": 0, "trailing_enter": False,
         "check_focus": False, "check_mouse": False}
    p.update(overrides)
    return p


def selftest():
    """无界面自检：引擎逻辑 + 参数实时生效 + 默认值。"""

    class FakeController:
        def __init__(self):
            self.typed = []
        def type(self, ch):
            self.typed.append(ch)

    def make_engine(fake):
        eng = TyperEngine()
        eng.controller = fake
        return eng

    states = []

    # 1) 基本输入 + 结尾回车
    fake = FakeController()
    eng = make_engine(fake)
    eng.start(text="Hello 你好\nWorld", params=_params(interval_ms=3, jitter_pct=50,
                                                     long_pause_pct=0, trailing_enter=True),
              on_status=lambda s: None, on_progress=lambda d, t: None,
              on_state=lambda st, r: states.append(st))
    eng.thread.join(timeout=30)
    assert not eng.running, "引擎未结束"
    assert "".join(fake.typed) == "Hello 你好\nWorld\n", f"注入内容不符: {fake.typed}"
    assert states[-1] == "done", f"状态异常: {states}"

    # 2) 暂停 -> 从断点继续
    fake2 = FakeController()
    eng2 = make_engine(fake2)
    text2 = "abcdef012345" * 5  # 60 字符
    eng2.start(text=text2, params=_params(interval_ms=15, jitter_pct=10, long_pause_pct=0),
               on_status=lambda s: None, on_progress=lambda d, t: None,
               on_state=lambda st, r: None)
    assert _wait_until(lambda: len(fake2.typed) >= 10), "未开始输入"
    eng2.pause("测试暂停")
    assert _wait_until(lambda: eng2.paused), "未进入暂停"
    time.sleep(0.2)
    n = len(fake2.typed)
    time.sleep(0.3)
    assert len(fake2.typed) == n, "暂停后仍在输入"
    eng2.resume()
    eng2.thread.join(timeout=30)
    assert "".join(fake2.typed) == text2, f"继续后内容不符: {''.join(fake2.typed)}"
    assert eng2.index == len(text2), "索引未走到末尾"

    # 3) 暂停 -> 从头开始
    fake3 = FakeController()
    eng3 = make_engine(fake3)
    text3 = "XYZ" * 20  # 60 字符
    eng3.start(text=text3, params=_params(interval_ms=15, jitter_pct=10, long_pause_pct=0),
               on_status=lambda s: None, on_progress=lambda d, t: None,
               on_state=lambda st, r: None)
    assert _wait_until(lambda: len(fake3.typed) >= 8), "未开始输入"
    eng3.pause("测试暂停")
    assert _wait_until(lambda: eng3.paused), "未进入暂停"
    time.sleep(0.2)
    n3 = len(fake3.typed)
    eng3.restart()
    eng3.thread.join(timeout=30)
    typed3 = "".join(fake3.typed)
    assert typed3 == typed3[:n3] + text3, f"从头开始结果不符: {typed3}"
    assert eng3.index == len(text3), "重打后索引未走到末尾"

    # 4) 参数实时生效：暂停时把间隔从 200ms 改成 2ms，继续后应快速完成
    fake4 = FakeController()
    eng4 = make_engine(fake4)
    p4 = _params(interval_ms=200, jitter_pct=0, long_pause_pct=0)
    text4 = "q" * 60
    eng4.start(text=text4, params=p4,
               on_status=lambda s: None, on_progress=lambda d, t: None,
               on_state=lambda st, r: None)
    assert _wait_until(lambda: len(fake4.typed) >= 3), "未开始输入"
    eng4.pause("测试暂停")
    assert _wait_until(lambda: eng4.paused), "未进入暂停"
    p4["interval_ms"] = 2  # 暂停期间修改速度
    t0 = time.monotonic()
    eng4.resume()
    eng4.thread.join(timeout=30)
    elapsed = time.monotonic() - t0
    assert "".join(fake4.typed) == text4, "续输内容不符"
    assert elapsed < 5, f"参数未实时生效，耗时 {elapsed:.1f}s 远超预期"

    # 5) 停止机制
    fake5 = FakeController()
    eng5 = make_engine(fake5)
    eng5.start(text="x" * 10000, params=_params(interval_ms=30, countdown_s=5),
               on_status=lambda s: None, on_progress=lambda d, t: None,
               on_state=lambda st, r: None)
    time.sleep(0.3)
    eng5.stop()
    eng5.thread.join(timeout=10)
    assert not eng5.running, "停止失败"

    # 6) 默认值
    assert DEFAULT_SETTINGS["interval"] == 15, "默认间隔应为 15ms"
    assert DEFAULT_SETTINGS["pause"] == 2, "默认长停顿概率应为 2%"

    print("SELFTEST OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--selftest", action="store_true", help="运行无界面自检后退出")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    enable_dpi_awareness()  # 必须在创建窗口前调用
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
