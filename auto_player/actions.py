"""动作执行 —— 把 Action 对象转成实际的鼠标/键盘操作。

所有点击坐标都是【屏幕绝对坐标】,由引擎把窗口内坐标 + 窗口偏移算好后传入。
$match 占位符在执行前由引擎替换成真实命中坐标。

注意:pyautogui 延迟导入,这样 --dry-run 在无显示器环境也能验证规则。
"""
import time
import random
from typing import Any

from rules import Action, Match
from humanize import jitter, random_delay, human_pause

# pyautogui 延迟导入:模块加载时不连显示器,dry-run 才不会炸
_pyautogui = None


def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        # 安全设置:鼠标移到屏幕左上角(0,0)立刻中断,防失控
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0  # 我们自己控制延迟
        _pyautogui = pyautogui
    return _pyautogui


class ActionExecutor:
    def __init__(self):
        self._key_map = {
            "space": "space", "enter": "enter", "esc": "escape",
            "tab": "tab", "ctrl": "ctrl", "alt": "alt", "shift": "shift",
            "up": "up", "down": "down", "left": "left", "right": "right",
        }

    def run(self, action: Action, match: Match = None) -> None:
        """执行单个动作。match 是当前规则命中的位置(供 $match 引用)。"""
        target = self._resolve_target(action.target, match)

        if action.kind == "click":
            self._click(target, action, button="left")
        elif action.kind == "double_click":
            self._click(target, action, button="left", clicks=2)
        elif action.kind == "right_click":
            self._click(target, action, button="right")
        elif action.kind == "drag":
            self._drag(action, match)
        elif action.kind == "key":
            self._key(target)
        elif action.kind == "type":
            ag = _get_pyautogui()
            ag.typewrite(str(target), interval=random.uniform(0.03, 0.08))
        elif action.kind == "wait":
            random_delay(target)
        else:
            raise ValueError(f"未知动作: {action.kind}")

        # 动作后的延迟(除了 wait,wait 自己已经等了)
        if action.kind != "wait" and action.delay:
            random_delay(action.delay)

    # ---------- 内部实现 ----------

    def _resolve_target(self, target: Any, match: Match) -> Any:
        """把 yaml 里的 $match 占位符解析成真实坐标。"""
        if target == "$match":
            if match is None:
                raise ValueError("规则用了 $match,但当前没有命中结果")
            x, y = match.x, match.y
            return (x, y)
        return target

    def _click(self, target, action: Action, button="left", clicks=1) -> None:
        if isinstance(target, str):
            raise ValueError(f"点击目标无法解析: {target}")
        x, y = target
        # 加偏移
        x += action.offset[0]
        y += action.offset[1]
        # 加抖动
        x, y = jitter((x, y), action.jitter)
        ag = _get_pyautogui()
        # 平滑移动更像人
        ag.moveTo(x, y, _tween())
        human_pause(0.02, 0.08)
        ag.click(x, y, button=button, clicks=clicks,
                 interval=random.uniform(0.05, 0.12) if clicks > 1 else 0)

    def _drag(self, action: Action, match: Match) -> None:
        frm = action.extra.get("from")
        to = action.extra.get("to")
        if frm == "$match":
            frm = (match.x, match.y)
        if to == "$match":
            to = (match.x, match.y)
        ag = _get_pyautogui()
        ag.moveTo(frm[0], frm[1], _tween())
        human_pause()
        ag.dragTo(to[0], to[1], duration=random.uniform(0.2, 0.4), button="left")

    def _key(self, target) -> None:
        ag = _get_pyautogui()
        # target 可以是 "space" 或 ["ctrl","c"]
        if isinstance(target, str):
            keys = [target]
        else:
            keys = list(target)
        keys = [self._key_map.get(k.lower(), k) for k in keys]
        if len(keys) == 1:
            ag.press(keys[0])
        else:
            ag.hotkey(*keys)


def _tween():
    """随机选一个移动轨迹函数,让鼠标移动更像人。"""
    ag = _get_pyautogui()
    return random.choice([ag.easeInQuad, ag.easeOutQuad, ag.easeInOutQuad])
