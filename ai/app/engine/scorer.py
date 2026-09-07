"""太极拳五要领评分器（17 关键点版）。

理念源自参考项目「承极」的静态五要领评分，适配 YOLO pose 的 COCO 17 点。
M3 接入课程关键帧模板后，在此之上叠加 DTW 序列对齐评分。
"""

from __future__ import annotations

from typing import Any

from app.engine.angles import (
    L_ANKLE,
    L_ELBOW,
    L_HIP,
    L_KNEE,
    L_SHOULDER,
    L_WRIST,
    R_ANKLE,
    R_ELBOW,
    R_HIP,
    R_KNEE,
    R_SHOULDER,
    R_WRIST,
    calc_angle,
)

CONF_THRESHOLD = 0.3


def _visible(kp: dict[str, float]) -> bool:
    return float(kp["v"]) > CONF_THRESHOLD


def _joint_angle(
    kp: list[dict[str, float]], joint: int, a: int, b: int
) -> float | None:
    """关节夹角；三点任一不可见时返回 None。"""
    if not (_visible(kp[joint]) and _visible(kp[a]) and _visible(kp[b])):
        return None
    return calc_angle(kp[a], kp[joint], kp[b])


def score_pose(keypoints: list[dict[str, float]]) -> dict[str, Any]:
    """输入 17 关键点 [{"x","y","v"}, ...]，返回五要领评分与建议。

    返回: {"score": float, "items": [...], "suggestions": [...]}
    不可见的评分项自动跳过（不参与平均），不出建议。
    """
    items: list[dict[str, Any]] = []
    suggestions: list[str] = []

    def add_angle_item(name: str, angle: float | None, item_fn) -> None:
        """item_fn(angle) -> (score, suggestion_or_None)"""
        if angle is None:
            return
        s, sug = item_fn(angle)
        items.append({"name": name, "score": s, "angle": round(angle, 1)})
        if sug:
            suggestions.append(sug)

    # --- 1. 坠肘 ---
    def elbow_rule(side: str):
        def rule(a: float):
            if 90 <= a <= 165:
                return 95, None
            if 80 <= a < 90 or 165 < a <= 175:
                return 78, f"{side}肘角度{a:.0f}°，注意沉肩坠肘"
            return 55, (
                f"{side}肘角度{a:.0f}°，{'过度弯曲' if a < 80 else '过于伸直'}，需调整"
            )
        return rule

    add_angle_item("左肘坠肘", _joint_angle(keypoints, L_ELBOW, L_SHOULDER, L_WRIST), elbow_rule("左"))
    add_angle_item("右肘坠肘", _joint_angle(keypoints, R_ELBOW, R_SHOULDER, R_WRIST), elbow_rule("右"))

    # --- 2. 屈膝 ---
    def knee_rule(side: str):
        def rule(a: float):
            if 115 <= a <= 165:
                return 95, None
            if 105 <= a < 115 or 165 < a <= 175:
                return 80, f"{side}膝角度{a:.0f}°，屈膝幅度可微调"
            return 55, (
                f"{side}膝角度{a:.0f}°，{'屈膝过度' if a < 105 else '膝盖过直'}，注意松胯屈膝"
            )
        return rule

    add_angle_item("左膝屈膝", _joint_angle(keypoints, L_KNEE, L_HIP, L_ANKLE), knee_rule("左"))
    add_angle_item("右膝屈膝", _joint_angle(keypoints, R_KNEE, R_HIP, R_ANKLE), knee_rule("右"))

    # --- 3. 身体中正（左右肩 / 左右髋的水平差） ---
    if all(_visible(keypoints[i]) for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)):
        tilt = max(
            abs(keypoints[L_SHOULDER]["y"] - keypoints[R_SHOULDER]["y"]),
            abs(keypoints[L_HIP]["y"] - keypoints[R_HIP]["y"]),
        )
        if tilt < 0.025:
            items.append({"name": "身体中正", "score": 96, "angle": None})
        elif tilt < 0.05:
            items.append({"name": "身体中正", "score": 82, "angle": None})
            suggestions.append("身体略有倾斜，注意立身中正")
        else:
            items.append({"name": "身体中正", "score": 60, "angle": None})
            suggestions.append("身体偏斜较大，注意中正安舒")

    # --- 4. 重心稳定（髋中点与双踝中点的水平偏移） ---
    if all(_visible(keypoints[i]) for i in (L_HIP, R_HIP, L_ANKLE, R_ANKLE)):
        hip_cx = (keypoints[L_HIP]["x"] + keypoints[R_HIP]["x"]) / 2
        foot_cx = (keypoints[L_ANKLE]["x"] + keypoints[R_ANKLE]["x"]) / 2
        balance = abs(hip_cx - foot_cx)
        if balance < 0.04:
            items.append({"name": "重心稳定", "score": 96, "angle": None})
        elif balance < 0.09:
            items.append({"name": "重心稳定", "score": 80, "angle": None})
            suggestions.append("重心略有偏移，注意虚实转换")
        else:
            items.append({"name": "重心稳定", "score": 62, "angle": None})
            suggestions.append("重心偏移较大，注意稳固下盘")

    # --- 5. 松胯 ---
    def hip_rule(side: str):
        def rule(a: float):
            if 100 <= a <= 150:
                return 92, None
            if 90 <= a < 100 or 150 < a <= 165:
                return 78, f"{side}髋角度{a:.0f}°，注意松胯"
            return 58, f"{side}髋角度{a:.0f}°，胯部需调整"
        return rule

    add_angle_item("左髋松胯", _joint_angle(keypoints, L_HIP, L_SHOULDER, L_KNEE), hip_rule("左"))
    add_angle_item("右髋松胯", _joint_angle(keypoints, R_HIP, R_SHOULDER, R_KNEE), hip_rule("右"))

    overall = (
        round(sum(i["score"] for i in items) / len(items), 1) if items else 0.0
    )
    if not suggestions:
        suggestions.append("整体拳架端正，继续保持！")
    return {"score": overall, "items": items, "suggestions": suggestions}
