"""健康检查"""

import time

from fastapi import APIRouter

from app import APP_NAME, APP_VERSION
from app.config import get_settings

router = APIRouter()


def detect_device() -> str:
    """探测推理设备。torch 未安装时返回 pending（M2 安装后自动变为 cuda/cpu）。"""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "pending"


@router.get("/api/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "device": detect_device(),
        "device_setting": settings.device,
        "model": settings.model_path,
        "timestamp": int(time.time() * 1000),
    }
