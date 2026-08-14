"""拟人化处理 —— 坐标抖动 + 随机延迟,避免被风控判定为机器人。"""
import random
import time


def jitter(point: tuple, radius: int) -> tuple:
    """对坐标加随机抖动。radius=0 时原样返回。"""
    if not radius:
        return point
    x, y = point
    return (x + random.randint(-radius, radius),
            y + random.randint(-radius, radius))


def random_delay(spec) -> float:
    """根据延迟规格等待,返回实际等待秒数。

    spec 可以是:
      None          -> 不等待
      float/int     -> 固定等待
      [min, max]    -> 随机等待区间
    """
    if spec is None:
        return 0.0
    if isinstance(spec, (int, float)):
        t = float(spec)
    else:
        t = random.uniform(spec[0], spec[1])
    time.sleep(t)
    return t


def human_pause(min_s: float = 0.05, max_s: float = 0.15) -> None:
    """模拟人的反应停顿,用在动作之间。"""
    time.sleep(random.uniform(min_s, max_s))
