"""课程会话引擎：实时帧与课程关键帧的达标保持 + 等待推进。

进度推进模式（区别于"姿势一匹配就跳下一拍"）：
1. 学员当前姿态与当前拍关键帧匹配分 ≥ HOLD_TH → 判定"动作完成"（hold_done）
2. 完成后等待 wait_ms（训练界面可设置，默认 3 秒）
3. 等待结束自动进入下一拍并播报口令；最后一拍完成则整套结束
"""

from __future__ import annotations

import random
import time
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
        ["左胯收回来一些", "注意收右胯"],
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

# 匹配分达到达标线（默认 75 ≈ 关节平均偏差 10°）判定当前动作完成，
# 训练界面可调（50-95）
DEFAULT_HOLD_TH = 75.0
DEFAULT_WAIT_MS = 3000
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
    def __init__(
        self,
        course: dict[str, Any],
        model: dict[str, Any],
        wait_ms: int = DEFAULT_WAIT_MS,
        hold_th: float = DEFAULT_HOLD_TH,
    ) -> None:
        self.course = course
        self.keyframes: list[dict[str, Any]] = model["keyframes"]
        self.duration_ms = model.get("duration_ms", 0)
        self.wait_ms = max(0, int(wait_ms))
        self.hold_th = min(95.0, max(50.0, float(hold_th)))
        self.cursor = 0
        self.completed = False  # 当前拍姿态已达标
        self.completed_at = 0.0  # 达标时刻（monotonic）
        self.pending_advance = False  # 跳过此拍：下一帧强制推进
        self.session_done = False  # 整套动作已完成

    @property
    def total(self) -> int:
        return len(self.keyframes)

    def set_wait(self, wait_ms: int) -> None:
        self.wait_ms = max(0, int(wait_ms))

    def set_hold_th(self, hold_th: float) -> None:
        self.hold_th = min(95.0, max(50.0, float(hold_th)))

    def reset(self) -> None:
        self.cursor = 0
        self.completed = False
        self.completed_at = 0.0
        self.pending_advance = False
        self.session_done = False

    def skip_phase(self) -> None:
        """跳过当前拍：直接推进（最后一拍则整套结束）。"""
        if self.session_done:
            return
        self.pending_advance = True

    def update(self, angles: dict[str, float]) -> dict[str, Any]:
        """输入当前帧角度，返回课程匹配结果。"""
        now = time.monotonic()
        dists = {
            i: _angle_distance(angles, kf["angles"])
            for i, kf in enumerate(self.keyframes)
        }

        d = dists[self.cursor]
        match_score = round(max(0.0, 100 - d * 2.5), 1)
        deviations = _deviations(angles, self.keyframes[self.cursor]["angles"])

        phase_changed = False
        finished = False
        hold_done = False
        hold_remaining: int | None = None

        if not self.session_done:
            if self.pending_advance:
                # 跳过此拍
                self.pending_advance = False
                self.completed = False
                self.completed_at = 0.0
                if self.cursor < self.total - 1:
                    self.cursor += 1
                    phase_changed = True
                else:
                    self.session_done = True
                    finished = True
            elif not self.completed:
                # 等待当前姿态达标
                if match_score >= self.hold_th:
                    self.completed = True
                    self.completed_at = now
                    hold_done = True
            else:
                # 已达标：等待 wait_ms 后进入下一拍
                elapsed_ms = (now - self.completed_at) * 1000
                remaining = self.wait_ms - elapsed_ms
                if remaining <= 0:
                    self.completed = False
                    self.completed_at = 0.0
                    if self.cursor < self.total - 1:
                        self.cursor += 1
                        phase_changed = True
                    else:
                        self.session_done = True
                        finished = True
                else:
                    hold_remaining = int(remaining)

        kf = self.keyframes[self.cursor]
        return {
            "phase": kf["index"],
            "phase_total": self.total,
            "cue": kf["cue"],
            "phase_changed": phase_changed,
            "finished": finished,
            "session_done": self.session_done,
            "hold_done": hold_done,
            "hold_remaining_ms": hold_remaining,
            "match_score": match_score,
            "progress": round((self.cursor + 1) / self.total, 3),
            "deviations": deviations,
            # 当前拍的标准姿态（归一化），转为 {"x","y","v"} 结构供前端叠加
            "ghost": [
                {"x": p[0], "y": p[1], "v": p[2]} if isinstance(p, (list, tuple)) else p
                for p in kf["pose"]
            ],
            # 姿态达标且无明显偏差：供前端做低频鼓励播报
            "all_good": len(deviations) == 0 and match_score >= GOOD_MATCH_TH,
        }
