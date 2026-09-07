"""课程模型提取（人工打标模式）。

管理员在前台视频预览中人工标记每一拍的时间戳（tMs + 口令），
本模块按标记的时间点定点提取教练姿态：YOLO 关键点 → 平滑 →
髋原点/躯干尺度归一化 → 关键帧（角度模板 + 容差 + 口令）→ 课程模型 JSON。
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

# 每个打点前后各取多少毫秒的帧做采样，取检测质量最好的一帧
SEEK_BACK_MS = 350
SAMPLE_WINDOW_MS = 700
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


def _detect_best_at(
    cap: cv2.VideoCapture, t_ms: int, engine
) -> tuple[list[dict[str, float]] | None, cv2.Mat | None]:
    """在 t_ms 附近采样若干帧，返回可见关键点最多的检测结果。"""
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_ms = max(0, t_ms - SEEK_BACK_MS)
    step_ms = max(1, 1000.0 / fps)
    n = max(1, int(SAMPLE_WINDOW_MS / step_ms))
    cap.set(cv2.CAP_PROP_POS_MSEC, start_ms)

    best_lm: list[dict[str, float]] | None = None
    best_frame: cv2.Mat | None = None
    best_visible = -1
    for i in range(n):
        ok, frame = cap.read()
        if not ok:
            break
        lm = engine.detect(frame)
        if lm:
            visible = sum(1 for p in lm if p["v"] > 0.3)
            if visible > best_visible:
                best_visible = visible
                best_lm = lm
                best_frame = frame.copy()
        if start_ms + i * step_ms > t_ms + SAMPLE_WINDOW_MS - SEEK_BACK_MS:
            break
    return best_lm, best_frame


def extract_at_markers(
    video_path: str,
    uploads_root: str,
    job_id: int,
    markers: list[dict[str, Any]],
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """按人工打点提取课程模型。

    markers: [{"tMs": 1200, "cue": "起势"}, ...]（已按时间升序）
    返回 {"model": {...}, "cover_url": "..."}。
    """
    engine = get_pose_engine()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ExtractError("无法读取视频文件")

    smoother = KeypointSmoother(alpha=0.9)  # 打点间相互独立，仅做轻微平滑
    keyframes: list[dict[str, Any]] = []
    skipped: list[str] = []
    cover_frame = None
    last_cb = time.perf_counter()

    for n, marker in enumerate(markers, start=1):
        t_ms = int(marker["tMs"])
        lm, frame = _detect_best_at(cap, t_ms, engine)
        if not lm:
            skipped.append(f"第 {n} 拍（{t_ms}ms）")
            continue
        smoothed = smoother.smooth(lm)
        keyframes.append(
            {
                "index": len(keyframes) + 1,
                "t_ms": t_ms,
                "pose": _normalize(smoothed),
                "angles": calculate_angles(smoothed),
                "tolerance": {
                    k: DEFAULT_TOLERANCE
                    for k, v in calculate_angles(smoothed).items()
                    if v >= 0
                },
                "cue": (marker.get("cue") or f"第 {len(keyframes) + 1} 拍").strip(),
            }
        )
        if cover_frame is None:
            cover_frame = frame

        if on_progress:
            done = n / len(markers) * 90
            now = time.perf_counter()
            if now - last_cb > 1.0:
                last_cb = now
                on_progress(done)
    cap.release()

    if not keyframes:
        raise ExtractError("所有打点均未能检测到人体，请确认示范者全身入镜后重新生成")
    if skipped:
        logger.warning("跳过未检测到人体的打点: %s", "、".join(skipped))

    model = {
        "version": 1,
        "duration_ms": keyframes[-1]["t_ms"],
        "keyframe_count": len(keyframes),
        "keyframes": keyframes,
    }

    cover_rel = os.path.join("covers", f"job_{job_id}.jpg")
    cover_path = os.path.join(uploads_root, cover_rel)
    os.makedirs(os.path.dirname(cover_path), exist_ok=True)
    cv2.imwrite(cover_path, cover_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

    on_progress and on_progress(95)
    return {
        "model": model,
        "cover_url": f"/api/uploads/{cover_rel.replace(os.sep, '/')}",
        "skipped": skipped,
    }


def save_model(model: dict[str, Any], course_id: int) -> str:
    """模型 JSON 落盘，返回绝对路径。"""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"
    )
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"course_{course_id}_v{model['version']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False)
    return path
