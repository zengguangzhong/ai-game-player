"""窗口管理 —— 定位游戏窗口、前台化、截取窗口画面。

依赖 pygetwindow + mss(高速截图)+ pywin32(Windows 窗口操作)。
在 Windows 上运行,游戏窗口必须可见(不能最小化)。
"""
import time
from typing import Optional

import numpy as np
import cv2

try:
    import mss
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False

try:
    import pygetwindow as gw
    _HAS_GW = True
except Exception:
    # pygetwindow 在非 Windows 平台会抛 NotImplementedError/ImportError
    _HAS_GW = False


class GameWindow:
    """游戏窗口句柄,提供截图和坐标基准。"""

    def __init__(self, title: str = "", resolution: tuple = (1920, 1080)):
        self.title = title
        self.resolution = resolution
        self._sct = mss.mss() if _HAS_MSS else None
        self._win = None
        if title:
            self._locate()

    def _locate(self):
        if not _HAS_GW:
            print("[window] pygetwindow 未安装,无法定位窗口,将使用全屏")
            return
        # 模糊匹配标题
        candidates = [w for w in gw.getAllWindows() if self.title.lower() in w.title.lower()]
        if not candidates:
            print(f"[window] 找不到标题含 '{self.title}' 的窗口,将使用全屏")
            return
        self._win = candidates[0]

    def bring_to_front(self) -> None:
        """把窗口提到最前并恢复大小。"""
        if self._win is None:
            return
        try:
            if self._win.isMinimized:
                self._win.restore()
            self._win.activate()
            time.sleep(0.3)
        except Exception as e:
            print(f"[window] 前台化失败: {e}")

    def get_rect(self) -> tuple:
        """返回窗口在屏幕上的 (left, top, width, height)。"""
        if self._win is None:
            # 全屏模式:用主显示器分辨率
            if _HAS_MSS:
                m = self._sct.monitors[1]
                return (m["left"], m["top"], m["width"], m["height"])
            return (0, 0, *self.resolution)
        return (self._win.left, self._win.top, self._win.width, self._win.height)

    def get_offset(self) -> tuple:
        """返回窗口左上角在屏幕上的坐标,用于把窗口内坐标转成屏幕绝对坐标。"""
        r = self.get_rect()
        return (r[0], r[1])

    def screenshot(self) -> np.ndarray:
        """截取当前窗口区域,返回 BGR ndarray(用于 OpenCV)。"""
        if not _HAS_MSS:
            # 退化方案:用 pyautogui 截全屏
            import pyautogui
            img = np.array(pyautogui.screenshot())
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        left, top, w, h = self.get_rect()
        # mss 要求 width/height 为正
        w = max(1, w)
        h = max(1, h)
        monitor = {"left": left, "top": top, "width": w, "height": h}
        raw = np.array(self._sct.grab(monitor))
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

    def close(self):
        if self._sct:
            self._sct.close()
