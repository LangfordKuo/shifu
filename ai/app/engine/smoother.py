"""关键点指数滑动平均（EMA）平滑，降低骨架抖动。

统一使用 {"x","y","v"} dict 结构（与推理引擎输出、WS 协议一致）。
"""

from __future__ import annotations

Landmark = dict[str, float]


class KeypointSmoother:
    def __init__(self, n_points: int = 17, alpha: float = 0.45) -> None:
        self.n = n_points
        self.alpha = alpha
        self._prev: list[Landmark] | None = None

    def reset(self) -> None:
        self._prev = None

    def smooth(self, landmarks: list[Landmark]) -> list[Landmark]:
        """输入当前帧关键点，输出平滑后的新列表（不修改入参）。"""
        cur = [
            {"x": float(p["x"]), "y": float(p["y"]), "v": float(p["v"])}
            for p in landmarks
        ]
        prev = self._prev
        if prev is None or len(prev) != len(cur):
            self._prev = cur
            return cur

        a = self.alpha
        out: list[Landmark] = []
        for p, q in zip(cur, prev):
            # 双帧均可见时做插值；否则以当前帧为准，避免残影
            if p["v"] > 0.3 and q["v"] > 0.3:
                out.append(
                    {
                        "x": round(a * p["x"] + (1 - a) * q["x"], 4),
                        "y": round(a * p["y"] + (1 - a) * q["y"], 4),
                        "v": p["v"],
                    }
                )
            else:
                out.append(p)
        self._prev = out
        return out
