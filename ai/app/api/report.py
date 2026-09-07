"""训练报告：学员动作序列与课程关键帧的对齐分析。

前端在课程训练中采集逐帧样本（时间、角度、匹配分、所在拍），
训练结束时提交到此接口，生成节奏对齐与分拍统计报告。
对齐采用与实时一致的"单调推进匹配"（DTW 简化版）产生的阶段轨迹。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from jwt import InvalidTokenError
import jwt as pyjwt
from pydantic import BaseModel, Field

from app.config import get_settings
from app.internal_client import get_course_model

logger = logging.getLogger("shifu.ai.report")
router = APIRouter()


class Sample(BaseModel):
    t: int = Field(ge=0, description="相对训练开始的毫秒数")
    score: float = Field(ge=0, le=100, description="五要领规范分")
    match: float | None = Field(default=None, ge=0, le=100, description="关键帧匹配分")
    phase: int | None = Field(default=None, ge=1, description="当前所处拍（1 起）")


class ReportRequest(BaseModel):
    course_id: int
    samples: list[Sample] = Field(min_length=3)


def _auth(token: str | None) -> None:
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        settings = get_settings()
        pyjwt.decode(
            token.replace("Bearer ", "", 1) if token.startswith("Bearer ") else token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_sub": False},
        )
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="登录已失效")


@router.post("/api/report")
async def generate_report(
    req: ReportRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    _auth(authorization)

    payload = get_course_model(req.course_id)
    model = payload["model"]
    keyframes: list[dict[str, Any]] = model["keyframes"]
    duration_ms = model.get("duration_ms", 0) or 1
    total = len(keyframes)

    # ---------- 分拍统计 ----------
    per_phase: dict[int, dict[str, Any]] = {}
    for s in req.samples:
        if s.phase is None:
            continue
        stat = per_phase.setdefault(
            s.phase, {"phase": s.phase, "frames": 0, "match_sum": 0.0, "score_sum": 0.0, "t_first": s.t, "t_last": s.t}
        )
        stat["frames"] += 1
        stat["match_sum"] += s.match or 0.0
        stat["score_sum"] += s.score
        stat["t_last"] = s.t

    phase_items: list[dict[str, Any]] = []
    reached = sorted(per_phase.keys())
    max_phase = max(reached) if reached else 0
    for kf in keyframes:
        p = kf["index"]
        stat = per_phase.get(p)
        ref_t = kf["t_ms"]
        if stat and stat["frames"] > 0:
            phase_items.append(
                {
                    "phase": p,
                    "cue": kf["cue"],
                    "match": round(stat["match_sum"] / stat["frames"], 1),
                    "form": round(stat["score_sum"] / stat["frames"], 1),
                    "duration_ms": stat["t_last"] - stat["t_first"],
                    "reference_ms": ref_t,
                    "arrive_ms": stat["t_first"],
                    "practiced": True,
                }
            )
        else:
            phase_items.append(
                {
                    "phase": p,
                    "cue": kf["cue"],
                    "match": None,
                    "form": None,
                    "duration_ms": 0,
                    "reference_ms": ref_t,
                    "arrive_ms": None,
                    "practiced": False,
                }
            )

    # ---------- 节奏对齐：到拍时间点 vs 参考时间比例 ----------
    rhythm_score: float | None = None
    if max_phase >= 1:
        devs: list[float] = []
        for item in phase_items:
            if not item["practiced"] or item["phase"] > max_phase:
                continue
            ref_frac = min(1.0, item["reference_ms"] / duration_ms)
            user_frac = min(1.0, item["arrive_ms"] / max(1, req.samples[-1].t))
            devs.append(abs(ref_frac - user_frac))
        if devs:
            mean_dev = sum(devs) / len(devs)
            rhythm_score = round(max(0.0, 100.0 - mean_dev * 250.0), 1)

    # ---------- 汇总 ----------
    practiced_items = [i for i in phase_items if i["practiced"]]
    form_avg = round(sum(s.score for s in req.samples) / len(req.samples), 1)
    match_avg = (
        round(sum(i["match"] for i in practiced_items) / len(practiced_items), 1)
        if practiced_items
        else None
    )
    coverage = round(len(practiced_items) / total, 3)

    overall = form_avg if match_avg is None else round(form_avg * 0.5 + match_avg * 0.5, 1)
    if rhythm_score is not None:
        overall = round(overall * 0.8 + rhythm_score * 0.2, 1)

    return {
        "type": "report",
        "overall": overall,
        "form": form_avg,
        "match": match_avg,
        "rhythm": rhythm_score,
        "coverage": coverage,
        "phases_practiced": len(practiced_items),
        "phase_total": total,
        "duration_ms": req.samples[-1].t,
        "phase_details": phase_items,
    }
