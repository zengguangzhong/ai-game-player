"""规则数据模型 —— 把 yaml 规则解析成强类型对象。

用户只需要写 yaml,引擎读这个模型执行。
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Match:
    """一次识别命中结果。"""
    x: int            # 命中区域中心 x(屏幕绝对坐标)
    y: int            # 命中区域中心 y(屏幕绝对坐标)
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0
    source: str = ""  # 命中的来源(图名/颜色/文字),便于日志


@dataclass
class Condition:
    """触发条件。支持 find_image / find_color / find_text / all / any。"""
    kind: str = "find_image"      # find_image | find_color | find_text | all | any
    value: Any = None             # 图路径 / 颜色hex / 文本 / 子条件列表
    confidence: float = 0.85
    region: Optional[tuple] = None  # (x,y,w,h) 限定搜索区域,None=全窗口

    @classmethod
    def from_dict(cls, d: dict) -> "Condition":
        if "all" in d:
            return cls(kind="all", value=[cls.from_dict(c) for c in d["all"]])
        if "any" in d:
            return cls(kind="any", value=[cls.from_dict(c) for c in d["any"]])
        if "find_image" in d:
            return cls(
                kind="find_image",
                value=d["find_image"],
                confidence=d.get("confidence", 0.85),
                region=tuple(d["region"]) if "region" in d else None,
            )
        if "find_color" in d:
            return cls(
                kind="find_color",
                value=d["find_color"],
                confidence=d.get("confidence", 0.9),
                region=tuple(d["region"]) if "region" in d else None,
            )
        if "find_text" in d:
            return cls(
                kind="find_text",
                value=d["find_text"],
                confidence=d.get("confidence", 0.8),
                region=tuple(d["region"]) if "region" in d else None,
            )
        raise ValueError(f"无法识别的条件: {d}")


@dataclass
class Action:
    """一个动作。click / double_click / right_click / drag / key / type / wait。"""
    kind: str
    target: Any = None        # $match / [x,y] / 文本 / 按键名
    jitter: int = 0           # 坐标随机抖动半径
    offset: tuple = (0, 0)    # 相对偏移
    delay: Optional[tuple] = None  # 动作后随机延迟区间 (min,max)
    extra: dict = field(default_factory=dict)  # drag 的 from/to、key 的组合键等

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        # yaml 里一行就是一个动作,键名=动作类型,值=目标
        # 例: {click: $match}  /  {key: space}  /  {wait: 1.0}
        kind = next(iter(d))
        body = d[kind]
        a = cls(kind=kind)
        if kind in ("click", "double_click", "right_click"):
            a.target = body
            a.jitter = d.get("jitter", 0)
            a.offset = tuple(d.get("offset", (0, 0)))
            a.delay = tuple(d["delay"]) if "delay" in d else None
        elif kind == "drag":
            a.extra = {"from": d.get("from"), "to": d.get("to")}
            a.delay = tuple(d["delay"]) if "delay" in d else None
        elif kind == "key":
            a.target = body  # "space" 或 ["ctrl","c"]
            a.delay = tuple(d["delay"]) if "delay" in d else None
        elif kind == "type":
            a.target = body
            a.delay = tuple(d["delay"]) if "delay" in d else None
        elif kind == "wait":
            # wait: 1.0  或  wait: [0.5, 1.5]
            a.target = body
        else:
            raise ValueError(f"未知的动作类型: {kind}")
        return a


@dataclass
class Rule:
    """一条完整规则:满足 when → 执行 then。"""
    name: str
    when: Condition
    then: list  # List[Action]
    priority: int = 0   # 数字越大越先判断
    cooldown: float = 0.0  # 触发后冷却秒数,避免同一规则狂点

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        actions = []
        for a in d.get("then", []):
            # 每个动作是一个 dict,如 {click: $match, jitter: 6, delay: [0.2,0.5]}
            # 也可能是裸标量,如 1.0(当成 wait:1.0)
            if not isinstance(a, dict):
                a = {"wait": a}
            actions.append(Action.from_dict(a))
        return cls(
            name=d.get("name", "未命名规则"),
            when=Condition.from_dict(d["when"]),
            then=actions,
            priority=d.get("priority", 0),
            cooldown=d.get("cooldown", 0.0),
        )


@dataclass
class GameConfig:
    """一个游戏的完整配置。"""
    game: str
    window_title: str = ""
    resolution: tuple = (1920, 1080)
    loop_interval: tuple = (0.3, 0.6)
    confidence: float = 0.85
    on_error: str = "continue"      # continue | restart | stop
    hotkey_stop: str = "ctrl+esc"
    rules: list = field(default_factory=list)  # List[Rule]

    @classmethod
    def from_dict(cls, d: dict) -> "GameConfig":
        cfg = cls(
            game=d.get("game", "未命名"),
            window_title=d.get("window", {}).get("title", ""),
            resolution=tuple(d.get("window", {}).get("resolution", (1920, 1080))),
            loop_interval=tuple(d.get("settings", {}).get("loop_interval", (0.3, 0.6))),
            confidence=d.get("settings", {}).get("confidence", 0.85),
            on_error=d.get("settings", {}).get("on_error", "continue"),
            hotkey_stop=d.get("settings", {}).get("hotkey_stop", "ctrl+esc"),
        )
        cfg.rules = [Rule.from_dict(r) for r in d.get("rules", [])]
        cfg.rules.sort(key=lambda r: -r.priority)  # 高优先级在前
        return cfg
