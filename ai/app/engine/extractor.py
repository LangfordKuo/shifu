"""课程模型提取管线（模板法）。

示范视频 → YOLO 逐帧关键点 → EMA 平滑 → 归一化 → 姿态变化速率切分关键帧
→ 课程模型 JSON（每关键帧的角度模板 + 容差 + 口令）+ 封面图。
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections.abc import Callable
from typing import Any

import cv2

from app.engine.angles import calculate_angles
from app.engine.pose_engine import get_pose_engine
from app.engine.smoother import KeypointSmoother

logger = logging.getLogger("shifu.ai.extract")

SAMPLE_FPS = 15  # 采样帧率
MIN_GAP_MS = 1500  # 关键帧最小间隔
VEL_TH = 10.0  # 关键帧候选的姿态变化阈值（平均角度差，度）
MAX_KEYFRAMES = 24
DEFAULT_TOLERANCE = 15.0  # 纠偏容差（度）


class ExtractError(Exception):
    """提取失败（含用户可读原因）。"""


def _normalize(landmarks: list[dict[str, float]]) -> list[list[float]]:
    """髋中点为原点、躯干长度为尺度归一化，消除距离/机位影响。"""
    pts = [(p["x"], p["y"]) for p in landmarks]
    hip_mid = ((pts[11][0] + pts[12][0]) / 2, (pts[11][1] + pts[12][1]) / 2)
    sh_mid = ((pts[5][0] + pts[6][0]) / 2, (pts[5][1] + pts[6][1]) / 2)
    scale = math.hypot(sh_mid[0] - hip_mid[0], sh_mid[1] - hip_mid[1])
    if scale < 1e-6:
        scale = 1.0
    return [
        [
            round((x - hip_mid[0]) / scale, 4),
            round((y - hip_mid[1]) / scale, 4),
            round(landmarks[i]["v"], 3),
        ]
        for i, (x, y) in enumerate(pts)
    ]


def _angle_distance(a: dict[str, float], b: dict[str, float]) -> float:
    """两个角度向量的平均绝对差（仅双方可见关节）；无可用关节返回 999。"""
    diffs = [
        abs(a[k] - b[k])
        for k in a
        if a[k] >= 0 and b.get(k, -1) >= 0
    ]
    return sum(diffs) / len(diffs) if diffs else 999.0


def extract(
    video_path: str,
    uploads_root: str,
    job_id: int,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """提取课程模型，返回 {"model": {...}, "cover_path": "..."}。"""
    engine = get_pose_engine()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ExtractError("无法读取视频文件")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, round(fps / SAMPLE_FPS))
    ms_per_sample = 1000.0 * step / fps

    smoother = KeypointSmoother(alpha=0.4)
    samples: list[dict[str, Any]] = []  # {t_ms, angles, pose}
    idx = -1
    last_cb = time.perf_counter()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % step != 0:
            continue

        small = frame
        h, w = small.shape[:2]
        if max(h, w) > 960:
            scale = 960 / max(h, w)
            small = cv2.resize(small, (int(w * scale), int(h * scale)))
        lm = engine.detect(small)
        if lm:
            smoothed = smoother.smooth(lm)
            samples.append(
                {
                    "t_ms": round(idx * 1000.0 / fps),
                    "angles": calculate_angles(smoothed),
                    "pose": _normalize(smoothed),
                    "frame": small.copy(),
                }
            )

        if on_progress and total_frames:
            done = (idx + 1) / total_frames * 80  # 推理占 0-80%
            now = time.perf_counter()
            if now - last_cb > 1.5:
                last_cb = now
                on_progress(done)
    cap.release()

    if len(samples) < 3:
        raise ExtractError("未能从视频中检测到稳定的人体动作，请确认示范者全身入镜")

    # ---------- 关键帧切分：姿态变化速率局部峰值 ----------
    vels = [0.0]
    for i in range(1, len(samples)):
        vels.append(_angle_distance(samples[i]["angles"], samples[i - 1]["angles"]))

    order = sorted(range(len(samples)), key=lambda i: vels[i], reverse=True)
    chosen: list[int] = []
    for i in order:
        if vels[i] < VEL_TH:
            break
        if all(abs(samples[i]["t_ms"] - samples[j]["t_ms"]) >= MIN_GAP_MS for j in chosen):
            chosen.append(i)
        if len(chosen) >= MAX_KEYFRAMES:
            break
    chosen.sort()
    if not chosen:
        chosen = [len(samples) // 2]  # 静态保持类动作取中段一帧
    # 保证首尾覆盖
    if chosen[0] != 0:
        chosen.insert(0, 0)
    if chosen[-1] != len(samples) - 1:
        chosen.append(len(samples) - 1)

    keyframes = []
    for n, i in enumerate(chosen, start=1):
        s = samples[i]
        keyframes.append(
            {
                "index": n,
                "t_ms": s["t_ms"],
                "pose": s["pose"],
                "angles": s["angles"],
                "tolerance": {k: DEFAULT_TOLERANCE for k, v in s["angles"].items() if v >= 0},
                "cue": f"第 {n} 拍",
            }
        )

    duration_ms = samples[-1]["t_ms"]
    model = {
        "version": 1,
        "sample_fps": round(fps / step, 2),
        "duration_ms": duration_ms,
        "keyframe_count": len(keyframes),
        "keyframes": keyframes,
    }

    # ---------- 封面：第一个关键帧（含骨架更直观，这里存原始帧） ----------
    cover_rel = os.path.join("covers", f"job_{job_id}.jpg")
    cover_path = os.path.join(uploads_root, cover_rel)
    os.makedirs(os.path.dirname(cover_path), exist_ok=True)
    cv2.imwrite(cover_path, samples[chosen[0]]["frame"], [cv2.IMWRITE_JPEG_QUALITY, 85])

    on_progress and on_progress(95)
    return {
        "model": model,
        "cover_url": f"/api/uploads/{cover_rel.replace(os.sep, '/')}",
    }


def save_model(model: dict[str, Any], course_id: int) -> str:
    """模型 JSON 落盘，返回绝对路径。"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models")
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"course_{course_id}_v{model['version']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)
    return path
