"""YOLO pose 推理封装：单例懒加载、设备自动探测、模型自动回退。"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import cv2
import numpy as np

from app.config import get_settings

logger = logging.getLogger("shifu.ai.pose")

# 候选模型按序尝试（首个存在的/可自动下载的生效）
MODEL_CANDIDATES = ["yolo26n-pose.pt", "yolo11n-pose.pt"]

_engine: "PoseEngine | None" = None


def resolve_device() -> str:
    """settings.device=auto 时探测 CUDA，否则明确指定。"""
    settings = get_settings()
    if settings.device != "auto":
        return settings.device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class PoseEngine:
    def __init__(self) -> None:
        from ultralytics import YOLO  # 延迟导入，加快服务启动

        settings = get_settings()
        self.device = resolve_device()
        self.model_path = self._resolve_model(settings.model_path)
        t0 = time.perf_counter()
        self.model = YOLO(self.model_path)
        logger.info(
            "模型加载完成: %s (device=%s, %.1fs)", self.model_path, self.device,
            time.perf_counter() - t0,
        )

    @staticmethod
    def _resolve_model(configured: str) -> str:
        # 配置路径存在则直接用；否则按候选列表让 ultralytics 自动下载
        if configured and os.path.exists(configured):
            return configured
        for cand in MODEL_CANDIDATES:
            if os.path.exists(cand):
                return cand
        return MODEL_CANDIDATES[-1]  # 交给 ultralytics 自动下载

    def detect(self, frame_bgr: np.ndarray) -> list[dict[str, float]] | None:
        """BGR 帧 -> 主人物 17 关键点（归一化坐标 + 置信度）；无人返回 None。"""
        results = self.model.predict(
            frame_bgr, device=self.device, verbose=False, conf=0.25,
        )
        r = results[0]
        if r.keypoints is None or r.keypoints.xyn is None or len(r.keypoints.xyn) == 0:
            return None

        # 多人时取检测置信度最高的那个
        if r.boxes is not None and len(r.boxes.conf) > 0:
            person = int(r.boxes.conf.argmax())
        else:
            person = 0

        xy = r.keypoints.xyn[person].cpu().numpy()  # (17, 2)
        conf = r.keypoints.conf
        cf = (
            conf[person].cpu().numpy()
            if conf is not None
            else np.ones(len(xy), dtype=float)
        )

        return [
            {"x": round(float(x), 4), "y": round(float(y), 4), "v": round(float(c), 3)}
            for (x, y), c in zip(xy, cf)
        ]

    def detect_bytes(self, jpeg: bytes) -> list[dict[str, float]] | None:
        buf = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        return self.detect(frame)


def get_pose_engine() -> "PoseEngine":
    global _engine
    if _engine is None:
        _engine = PoseEngine()
    return _engine


def engine_summary() -> dict[str, Any]:
    """健康检查用：不触发加载。"""
    settings = get_settings()
    from app.api.health import detect_device

    return {
        "device": detect_device(),
        "device_setting": settings.device,
        "model": settings.model_path,
        "loaded": _engine is not None,
    }
