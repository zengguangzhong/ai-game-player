"""识别器 —— 在截图里找图/找色/找文字,返回 Match。

全部基于 OpenCV,可选 OCR(pytesseract)。
所有坐标返回的都是【窗口区域内坐标】(以窗口左上角为原点),
由调用方(引擎)加上窗口偏移转成屏幕绝对坐标。
"""
import cv2
import numpy as np
from typing import Optional

from rules import Match


class ImageFinder:
    """模板匹配找图。最常用的识别方式。"""

    def __init__(self):
        self._cache = {}  # 模板图缓存,避免反复读盘

    def _load(self, path: str):
        if path not in self._cache:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"模板图读不到: {path}")
            self._cache[path] = img
        return self._cache[path]

    def find(self, screen_bgr: np.ndarray, template_path: str,
             confidence: float = 0.85,
             region: Optional[tuple] = None) -> Optional[Match]:
        """在 screen_bgr 里找 template_path。

        region: (x, y, w, h) 限定搜索区域(窗口内坐标),None=全图。
        返回 Match 或 None。
        """
        templ = self._load(template_path)
        h, w = templ.shape[:2]

        search_area = screen_bgr
        offset_x, offset_y = 0, 0
        if region:
            x, y, rw, rh = region
            search_area = screen_bgr[y:y + rh, x:x + rw]
            offset_x, offset_y = x, y

        # 灰度匹配,速度快且对色相微变鲁棒
        res = cv2.matchTemplate(
            cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(templ, cv2.COLOR_BGR2GRAY),
            cv2.TM_CCOEFF_NORMED,
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < confidence:
            return None

        left = max_loc[0] + offset_x
        top = max_loc[1] + offset_y
        return Match(
            x=left + w // 2,
            y=top + h // 2,
            left=left, top=top, width=w, height=h,
            confidence=float(max_val),
            source=template_path,
        )


class ColorFinder:
    """多点找色 —— 找指定颜色像素,适合固定 UI 色块。"""

    def find(self, screen_bgr: np.ndarray, hex_color: str,
             tolerance: int = 10,
             region: Optional[tuple] = None) -> Optional[Match]:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        target = np.array([b, g, r], dtype=np.uint8)  # OpenCV 是 BGR

        area = screen_bgr
        ox, oy = 0, 0
        if region:
            x, y, rw, rh = region
            area = screen_bgr[y:y + rh, x:x + rw]
            ox, oy = x, y

        dist = np.abs(area.astype(np.int16) - target).sum(axis=2)
        mask = dist <= tolerance * 3
        if not mask.any():
            return None
        ys, xs = np.where(mask)
        cx = int(xs.mean()) + ox
        cy = int(ys.mean()) + oy
        return Match(x=cx, y=cy, confidence=1.0, source=hex_color)


class TextFinder:
    """OCR 找文字(可选)。需要安装 pytesseract + Tesseract OCR 引擎。

    没装也不影响主流程,import 失败时这个类不可用。
    """
    def __init__(self):
        try:
            import pytesseract
            self._pytesseract = pytesseract
            self._available = True
        except ImportError:
            self._available = False

    def find(self, screen_bgr: np.ndarray, text: str,
             region: Optional[tuple] = None) -> Optional[Match]:
        if not self._available:
            return None
        area = screen_bgr
        ox, oy = 0, 0
        if region:
            x, y, rw, rh = region
            area = screen_bgr[y:y + rh, x:x + rw]
            ox, oy = x, y
        gray = cv2.cvtColor(area, cv2.COLOR_BGR2GRAY)
        data = self._pytesseract.image_to_data(
            gray, output_type=self._pytesseract.Output.DICT, lang="chi_sim+eng"
        )
        for i, w in enumerate(data["text"]):
            if text in w:
                x, y, w_, h_ = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                return Match(
                    x=x + w_ // 2 + ox, y=y + h_ // 2 + oy,
                    left=x + ox, top=y + oy, width=w_, height=h_,
                    confidence=float(data["conf"][i]) / 100,
                    source=text,
                )
        return None


class FinderHub:
    """统一入口,按 Condition.kind 分发到对应识别器。"""

    def __init__(self):
        self.image = ImageFinder()
        self.color = ColorFinder()
        self.text = TextFinder()

    def match(self, condition, screen_bgr: np.ndarray) -> Optional[Match]:
        from rules import Condition
        if condition.kind == "find_image":
            return self.image.find(screen_bgr, condition.value,
                                   condition.confidence, condition.region)
        if condition.kind == "find_color":
            return self.color.find(screen_bgr, condition.value, region=condition.region)
        if condition.kind == "find_text":
            return self.text.find(screen_bgr, condition.value, condition.region)
        if condition.kind == "all":
            last = None
            for c in condition.value:
                m = self.match(c, screen_bgr)
                if m is None:
                    return None
                last = m
            return last  # 全部满足时返回最后一个命中(用于 $match)
        if condition.kind == "any":
            for c in condition.value:
                m = self.match(c, screen_bgr)
                if m:
                    return m
            return None
        raise ValueError(f"未知条件类型: {condition.kind}")
