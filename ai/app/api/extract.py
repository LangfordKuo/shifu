"""课程模型提取接口：管理员人工打标后，按标记时间戳定点提取。"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.engine.extractor import ExtractError, extract_at_markers, save_model
from app.internal_client import update_job

logger = logging.getLogger("shifu.ai.extract")
router = APIRouter()


class Marker(BaseModel):
    tMs: int = Field(ge=0)
    cue: str = ""


class ExtractMarkersRequest(BaseModel):
    job_id: int
    course_id: int
    video_path: str
    uploads_root: str
    markers: list[Marker] = Field(min_length=1)


def _check_token(token: str | None) -> None:
    expected = get_settings().internal_token
    if token != expected:
        raise HTTPException(status_code=403, detail="内部令牌无效")


@router.post("/api/extract-markers")
def trigger_extract_markers(
    req: ExtractMarkersRequest,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _check_token(x_internal_token)
    markers = sorted(req.markers, key=lambda m: m.tMs)

    def run() -> None:
        try:
            result = extract_at_markers(
                req.video_path,
                req.uploads_root,
                req.job_id,
                [m.model_dump() for m in markers],
                on_progress=lambda p: update_job(req.job_id, status="RUNNING", progress=p),
            )
            model_path = save_model(result["model"], req.course_id)
            update_job(
                req.job_id,
                status="SUCCESS",
                progress=100,
                result={
                    "modelPath": model_path,
                    "keyframeCount": result["model"]["keyframe_count"],
                    "durationMs": result["model"]["duration_ms"],
                    "coverUrl": result["cover_url"],
                },
            )
            logger.info(
                "课程 %s 提取完成：%s 个关键帧（跳过 %s 个无效打点）",
                req.course_id,
                result["model"]["keyframe_count"],
                len(result["skipped"]),
            )
        except ExtractError as e:
            logger.warning("课程 %s 提取失败：%s", req.course_id, e)
            update_job(req.job_id, status="FAILED", error=str(e))
        except Exception:
            logger.exception("课程 %s 提取异常", req.course_id)
            update_job(req.job_id, status="FAILED", error="提取过程发生内部错误")

    threading.Thread(target=run, daemon=True, name=f"extract-{req.job_id}").start()
    return {"accepted": True}
