"""关节角度计算工具。

YOLO-pose 输出 COCO 17 个关键点：
  0 鼻  1/2 左/右眼  3/4 左/右耳
  5/6 左/右肩  7/8 左/右肘  9/10 左/右腕
  11/12 左/右髋  13/14 左/右膝  15/16 左/右踝

关键点统一为 {"x", "y", "v"} dict 结构（与推理引擎输出、WS 协议一致）。
评分引擎（五要领：坠肘/屈膝/中正/重心/松胯）基于本模块计算角度。
"""

from __future__ import annotations

import math
from typing import Sequence

# 关键点索引常量
NOSE = 0
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16

# 关节定义：(关节点, 端点A, 端点B)
JOINTS: dict[str, tuple[int, int, int]] = {
    "left_elbow": (L_ELBOW, L_SHOULDER, L_WRIST),
    "right_elbow": (R_ELBOW, R_SHOULDER, R_WRIST),
    "left_shoulder": (L_SHOULDER, L_ELBOW, L_HIP),
    "right_shoulder": (R_SHOULDER, R_ELBOW, R_HIP),
    "left_hip": (L_HIP, L_SHOULDER, L_KNEE),
    "right_hip": (R_HIP, R_SHOULDER, R_KNEE),
    "left_knee": (L_KNEE, L_HIP, L_ANKLE),
    "right_knee": (R_KNEE, R_HIP, R_ANKLE),
}

Landmark = dict[str, float]
CONF_THRESHOLD = 0.3


def calc_angle(
    a: Sequence[float] | Landmark,
    b: Sequence[float] | Landmark,
    c: Sequence[float] | Landmark,
) -> float:
    """计算点 b 处的夹角（度）。点为 (x, y)、(x, y, conf) 或 {"x","y"} dict。"""

    def xy(p) -> tuple[float, float]:
        if isinstance(p, dict):
            return float(p["x"]), float(p["y"])
        return float(p[0]), float(p[1])

    (ax, ay), (bx, by), (cx, cy) = xy(a), xy(b), xy(c)
    ab = (ax - bx, ay - by)
    bc = (cx - bx, cy - by)
    na = math.hypot(*ab)
    nb = math.hypot(*bc)
    if na == 0 or nb == 0:
        return 0.0
    cos_v = max(-1.0, min(1.0, (ab[0] * bc[0] + ab[1] * bc[1]) / (na * nb)))
    return math.degrees(math.acos(cos_v))


def calculate_angles(keypoints: Sequence[Landmark]) -> dict[str, float]:
    """输入 17 关键点，输出 8 个关节角度（度）；关节不可见时为 -1。"""
    result: dict[str, float] = {}
    for name, (joint, ia, ib) in JOINTS.items():
        a, b, c = keypoints[ia], keypoints[joint], keypoints[ib]
        if (
            a["v"] > CONF_THRESHOLD
            and b["v"] > CONF_THRESHOLD
            and c["v"] > CONF_THRESHOLD
        ):
            result[name] = round(calc_angle(a, b, c), 1)
        else:
            result[name] = -1.0
    return result
