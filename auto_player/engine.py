"""核心引擎 —— 规则循环 + 状态机 + 异常恢复。

主循环逻辑:
  1. 截取游戏窗口画面
  2. 按 priority 顺序遍历规则
  3. 命中规则 → 执行其 then 动作序列
  4. 进入冷却,本轮结束,等待下个循环
  5. 没命中任何规则 → 静默等待 loop_interval
  6. 出错按 on_error 策略处理
"""
import time
import random
import threading

from rules import GameConfig, Rule, Match
from finders import FinderHub
from actions import ActionExecutor
from window import GameWindow
from humanize import random_delay


def _fail_safe_exc():
    """延迟获取 pyautogui 的 FailSafeException,无显示器环境不报错。"""
    try:
        import pyautogui
        return pyautogui.FailSafeException
    except Exception:
        # 装不上 pyautogui 的环境,返回一个永远不会命中的异常类
        class _Dummy(Exception):
            pass
        return _Dummy


class Engine:
    def __init__(self, config: GameConfig):
        self.cfg = config
        self.finder = FinderHub()
        self.executor = ActionExecutor()
        self.window = GameWindow(config.window_title, config.resolution)
        self._last_trigger: dict[str, float] = {}  # 规则名 -> 上次触发时间(冷却用)
        self._stop_flag = threading.Event()
        self._loop_count = 0
        self._fail_safe = _fail_safe_exc()

    # ---------- 公共接口 ----------

    def start(self) -> None:
        """启动主循环,阻塞直到停止。"""
        print(f"[engine] 启动游戏自动化: {self.cfg.game}")
        print(f"[engine] 规则数: {len(self.cfg.rules)}")
        print(f"[engine] 窗口: '{self.cfg.window_title or '全屏'}'")
        print("[engine] 紧急停止: 把鼠标快速甩到屏幕左上角(0,0)")
        print("-" * 50)

        self.window.bring_to_front()
        time.sleep(1.0)

        try:
            while not self._stop_flag.is_set():
                self._loop_once()
        except KeyboardInterrupt:
            print("\n[engine] 用户中断")
        except self._fail_safe:
            print("\n[engine] 触发紧急停止(鼠标到左上角)")
        finally:
            self.window.close()
            print("[engine] 已停止")

    def stop(self) -> None:
        self._stop_flag.set()

    # ---------- 主循环 ----------

    def _loop_once(self) -> None:
        self._loop_count += 1
        try:
            screen = self.window.screenshot()
            offset = self.window.get_offset()

            for rule in self.cfg.rules:
                if self._in_cooldown(rule):
                    continue
                match = self.finder.match(rule.when, screen)
                if match is None:
                    continue

                # 把窗口内坐标转成屏幕绝对坐标
                match.x += offset[0]
                match.y += offset[1]
                match.left += offset[0]
                match.top += offset[1]

                self._fire(rule, match)
                self._last_trigger[rule.name] = time.time()
                # 命中一条规则就结束本轮(避免一帧内连点多个按钮)
                break
            else:
                # 本轮没命中任何规则
                self._sleep_loop()

        except self._fail_safe:
            raise
        except Exception as e:
            self._handle_error(e)

    def _fire(self, rule: Rule, match: Match) -> None:
        """执行一条规则的全部动作。"""
        print(f"[fire] {rule.name}  (conf={match.confidence:.2f} src={match.source})")
        for action in rule.then:
            try:
                self.executor.run(action, match)
            except Exception as e:
                print(f"[fire] 动作执行失败 {action.kind}: {e}")
                if self.cfg.on_error == "stop":
                    self.stop()

    # ---------- 辅助 ----------

    def _in_cooldown(self, rule: Rule) -> bool:
        if rule.cooldown <= 0:
            return False
        last = self._last_trigger.get(rule.name)
        if last is None:
            return False
        return (time.time() - last) < rule.cooldown

    def _sleep_loop(self) -> None:
        lo, hi = self.cfg.loop_interval
        time.sleep(random.uniform(lo, hi))

    def _handle_error(self, e: Exception) -> None:
        print(f"[error] {type(e).__name__}: {e}")
        mode = self.cfg.on_error
        if mode == "stop":
            self.stop()
        elif mode == "restart":
            print("[error] 尝试恢复:重新前台化窗口")
            self.window.bring_to_front()
            time.sleep(2.0)
        else:  # continue
            time.sleep(1.0)
