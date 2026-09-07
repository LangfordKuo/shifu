"""Node 业务服务内部调用（任务进度回调 / 课程模型拉取）。"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger("shifu.ai.node")

TIMEOUT = 15


def _headers() -> dict[str, str]:
    token = get_settings().internal_token
    return {"X-Internal-Token": token}


def update_job(
    job_id: int,
    *,
    status: str | None = None,
    progress: float | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> bool:
    """回调 Node 更新任务状态；失败仅记日志（任务可由管理端看到超时）。"""
    settings = get_settings()
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if progress is not None:
        payload["progress"] = round(progress)
    if error is not None:
        payload["error"] = error
    if result is not None:
        payload["result"] = result
    try:
        resp = requests.patch(
            f"{settings.node_base_url}/api/internal/jobs/{job_id}",
            json=payload,
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.warning("任务回调失败 %s: %s %s", job_id, resp.status_code, resp.text[:200])
            return False
        return True
    except requests.RequestException as e:
        logger.warning("任务回调异常 %s: %s", job_id, e)
        return False


def get_course_model(course_id: int) -> dict[str, Any]:
    """拉取课程模型（含课程标题）。失败抛异常，由 WS 层转错误消息。"""
    settings = get_settings()
    resp = requests.get(
        f"{settings.node_base_url}/api/internal/courses/{course_id}/model",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
