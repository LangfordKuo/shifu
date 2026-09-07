"""课程会话引擎：实时帧与课程关键帧的最近段跟踪 + 偏差纠正建议。

一期采用"单调推进的最近邻匹配"（lookahead 窗口内搜索最相似关键帧），
替代完整 DTW 以满足实时性；训练结束后的整段 DTW 对齐在 M4 增强。
"""

from __future__ import annotations

from typing import Any

# 纠偏口令表：joint -> (名称, 目标>当前时的动作, 目标<当前时的动作)
_PHRASES: dict[str, tuple[str, str, str]] = {
    "left_elbow": ("左肘", "再打开一些", "再收拢一些"),
    "right_elbow": ("右肘", "再打开一些", "再收拢一些"),
    "left_shoulder": ("左肩", "再抬高一些", "再放下一些"),
    "right_shoulder": ("右肩", "再抬高一些", "再放下一些"),
    "left_hip": ("左胯", "再松沉一些", "再收拢一些"),
    "right_hip": ("右胯", "再松沉一些", "再收拢一些"),
    "left_knee": ("左膝", "再伸直一些", "再屈膝一些"),
    "right_knee": ("右膝", "再伸直一些", "再屈膝一些"),
}

LOOKAHEAD = 6  # 允许向前跳跃匹配的关键帧数
ENTER_TH = 18.0  # 平均角度差小于该值（度）视为到达
MATCH_TH = 15.0  # 单关节偏差超过该值（度）才纠偏
MAX_DEVIATIONS = 3


def _angle_distance(a: dict[str, float], b: dict[str, float]) -> float:
    diffs = [abs(a[k] - b[k]) for k in a if a[k] >= 0 and b.get(k, -1) >= 0]
    return sum(diffs) / len(diffs) if diffs else 999.0


def _deviations(
    actual: dict[str, float], target: dict[str, float]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for joint, ta in _PHRASES.items():
        t = target.get(joint, -1)
        a = actual.get(joint, -1)
        if t < 0 or a < 0:
            continue
        delta = abs(a - t)
        if delta > MATCH_TH:
            name, more, less = ta
            word = more if t > a else less
            items.append(
                {
                    "joint": joint,
                    "name": name,
                    "target": round(t),
                    "actual": round(a),
                    "delta": round(delta, 1),
                    "text": f"{name}{word}（目标约{t:.0f}°，当前{a:.0f}°）",
                }
            )
    items.sort(key=lambda x: x["delta"], reverse=True)
    return items[:MAX_DEVIATIONS]


class CourseSession:
    def __init__(self, course: dict[str, Any], model: dict[str, Any]) -> None:
        self.course = course
        self.keyframes: list[dict[str, Any]] = model["keyframes"]
        self.duration_ms = model.get("duration_ms", 0)
        self.cursor = 0

    @property
    def total(self) -> int:
        return len(self.keyframes)

    def update(self, angles: dict[str, float]) -> dict[str, Any]:
        """输入当前帧角度，返回课程匹配结果。"""
        dists = {i: _angle_distance(angles, kf["angles"]) for i, kf in enumerate(self.keyframes)}
        best, best_d = self.cursor, dists[self.cursor]
        hi = min(self.total, self.cursor + 1 + LOOKAHEAD)
        for i in range(self.cursor + 1, hi):
            if dists[i] < best_d:
                best, best_d = i, dists[i]
        phase_changed = best > self.cursor and best_d <= ENTER_TH
        if phase_changed:
            self.cursor = best

        kf = self.keyframes[self.cursor]
        match_score = round(max(0.0, 100 - dists[self.cursor] * 2.5), 1)
        return {
            "phase": kf["index"],
            "phase_total": self.total,
            "cue": kf["cue"],
            "phase_changed": phase_changed,
            "match_score": match_score,
            "progress": round((self.cursor + 1) / self.total, 3),
            "deviations": _deviations(angles, kf["angles"]),
        }
