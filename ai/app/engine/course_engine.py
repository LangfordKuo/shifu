"""课程会话引擎：实时帧与课程关键帧的最近段跟踪 + 偏差纠正建议。

一期采用"单调推进的最近邻匹配"（lookahead 窗口内搜索最相似关键帧），
替代完整 DTW 以满足实时性；训练结束后的整段 DTW 对齐在 M4 增强。
"""

from __future__ import annotations

import random
from typing import Any

# 纠偏口令表：joint -> (名称, 目标>当前时的候选说法, 目标<当前时的候选说法)
# spoken 字段为面向 TTS 的口语短句（不带数字），text 为面向屏幕的详细描述
_PHRASES: dict[str, tuple[str, list[str], list[str]]] = {
    "left_elbow": (
        "左肘",
        ["左肘再打开一些", "左肘稍微抬高一点", "注意左肘，向外打开"],
        ["左肘再收拢一些", "左肘稍微收一点", "注意收一收左肘"],
    ),
    "right_elbow": (
        "右肘",
        ["右肘再打开一些", "右肘稍微抬高一点", "注意右肘，向外打开"],
        ["右肘再收拢一些", "右肘稍微收一点", "注意收一收右肘"],
    ),
    "left_shoulder": (
        "左肩",
        ["左肩再抬起一些", "注意沉左肩，动作放开"],
        ["左肩放松下沉一些", "左肩别耸太高，放松"],
    ),
    "right_shoulder": (
        "右肩",
        ["右肩再抬起一些", "注意沉右肩，动作放开"],
        ["右肩放松下沉一些", "右肩别耸太高，放松"],
    ),
    "left_hip": (
        "左胯",
        ["左胯再松沉一些", "沉一沉左胯"],
        ["左胯收回来一些", "注意收左胯"],
    ),
    "right_hip": (
        "右胯",
        ["右胯再松沉一些", "沉一沉右胯"],
        ["右胯收回来一些", "注意收右胯"],
    ),
    "left_knee": (
        "左膝",
        ["左膝再伸直一些", "左腿蹬直一点"],
        ["左膝再屈一些", "左膝再弯一点，别绷太直"],
    ),
    "right_knee": (
        "右膝",
        ["右膝再伸直一些", "右腿蹬直一点"],
        ["右膝再屈一些", "右膝再弯一点，别绷太直"],
    ),
}

PRAISE_POOL = [
    "很好，保持这个姿态",
    "不错，就是这样",
    "姿态很标准，继续",
    "棒，就是这个感觉",
]

LOOKAHEAD = 6  # 允许向前跳跃匹配的关键帧数
ENTER_TH = 18.0  # 平均角度差小于该值（度）视为到达
MATCH_TH = 15.0  # 单关节偏差超过该值（度）才纠偏
GOOD_MATCH_TH = 80.0  # 视为"做得好"的匹配分阈值
MAX_DEVIATIONS = 3


def _angle_distance(a: dict[str, float], b: dict[str, float]) -> float:
    diffs = [abs(a[k] - b[k]) for k in a if a[k] >= 0 and b.get(k, -1) >= 0]
    return sum(diffs) / len(diffs) if diffs else 999.0


def _deviations(
    actual: dict[str, float], target: dict[str, float]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for joint, (name, more_pool, less_pool) in _PHRASES.items():
        t = target.get(joint, -1)
        a = actual.get(joint, -1)
        if t < 0 or a < 0:
            continue
        delta = abs(a - t)
        if delta > MATCH_TH:
            pool = more_pool if t > a else less_pool
            spoken = random.choice(pool)
            items.append(
                {
                    "joint": joint,
                    "name": name,
                    "target": round(t),
                    "actual": round(a),
                    "delta": round(delta, 1),
                    # 屏幕显示：口语短句 + 目标数据
                    "text": f"{spoken}（目标约{t:.0f}°，当前{a:.0f}°）",
                    # 语音播报：口语短句，不带数字
                    "spoken": spoken,
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
        deviations = _deviations(angles, kf["angles"])
        finished = phase_changed and self.cursor == self.total - 1

        return {
            "phase": kf["index"],
            "phase_total": self.total,
            "cue": kf["cue"],
            "phase_changed": phase_changed,
            "finished": finished,
            "match_score": match_score,
            "progress": round((self.cursor + 1) / self.total, 3),
            "deviations": deviations,
            # 当前拍的标准姿态（归一化），前端叠加到学员身上做对比
            "ghost": kf["pose"],
            # 姿态达标且无明显偏差：供前端做低频鼓励播报
            "all_good": len(deviations) == 0 and match_score >= GOOD_MATCH_TH,
        }
