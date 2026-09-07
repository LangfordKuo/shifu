"""实时训练 WebSocket：JWT 鉴权 + 帧推理 + 评分 + 课程模式（关键帧跟踪）。

协议：
  客户端 -> 服务端:
    {"type": "auth", "token": "<JWT>"}          连接后 10s 内必须发送
    {"type": "start_course", "courseId": 123}   进入课程模式（自由训练无需发送）
    {"type": "stop_course"}                     退出课程模式回自由训练
    {"type": "reset"}                           重置平滑器与课程进度
    {"type": "ping"}
    二进制帧 = JPEG 图片
  服务端 -> 客户端:
    {"type": "auth_ok", "username": "..."}
    {"type": "course_loaded", "courseId": 123, "title": "...",
     "phase_total": 8, "durationMs": 42000}
    {"type": "result", "landmarks": [...], "angles": {...},
     "score": 88.5, "suggestions": ["..."],
     "phase": 2, "phase_total": 8, "cue": "第 2 拍",
     "phase_changed": true, "match_score": 91.2, "progress": 0.25,
     "deviations": [{"joint": "left_elbow", "text": "..."}],
     "inference_ms": 21.3}
    {"type": "result", "error": "no_person"}
    {"type": "pong"} / {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.engine.angles import calculate_angles
from app.engine.course_engine import CourseSession
from app.engine.pose_engine import get_pose_engine
from app.engine.scorer import score_pose
from app.engine.smoother import KeypointSmoother
from app import internal_client

logger = logging.getLogger("shifu.ai.ws")
router = APIRouter()


@router.websocket("/ws/train")
async def train(ws: WebSocket) -> None:
    await ws.accept()
    settings = get_settings()

    # ---------- 鉴权（共享 JWT_SECRET 模式） ----------
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
        auth = json.loads(raw)
        # verify_sub=False：兼容历史签发的数字 sub（签名始终强校验）
        payload = pyjwt.decode(
            auth.get("token", ""),
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_sub": False},
        )
    except Exception:
        await ws.send_json({"type": "error", "message": "鉴权失败，请重新登录"})
        await ws.close(code=4401)
        return

    await ws.send_json(
        {"type": "auth_ok", "username": payload.get("username", "unknown")}
    )
    logger.info("训练连接建立: %s", payload.get("username"))

    smoother = KeypointSmoother()
    course_session: CourseSession | None = None
    loop = asyncio.get_running_loop()

    def _infer(data: bytes):
        engine = get_pose_engine()  # 首帧懒加载模型
        return engine.detect_bytes(data)

    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break

            data = message.get("bytes")
            text = message.get("text")

            if text is not None:
                try:
                    ctrl = json.loads(text)
                except json.JSONDecodeError:
                    continue
                ctype = ctrl.get("type")
                if ctype == "start_course":
                    try:
                        payload_cm = internal_client.get_course_model(
                            int(ctrl.get("courseId", 0))
                        )
                        course_session = CourseSession(
                            payload_cm["course"], payload_cm["model"]
                        )
                        await ws.send_json(
                            {
                                "type": "course_loaded",
                                "courseId": course_session.course["id"],
                                "title": course_session.course["title"],
                                "phase_total": course_session.total,
                                "durationMs": course_session.duration_ms,
                            }
                        )
                    except Exception as e:
                        course_session = None
                        await ws.send_json(
                            {
                                "type": "error",
                                "message": f"课程加载失败：{e}",
                            }
                        )
                elif ctype == "stop_course":
                    course_session = None
                    await ws.send_json({"type": "course_stopped"})
                elif ctype == "reset":
                    smoother.reset()
                    if course_session:
                        course_session.cursor = 0
                    await ws.send_json({"type": "reset_ok"})
                elif ctype == "ping":
                    await ws.send_json({"type": "pong", "ts": int(time.time() * 1000)})
                continue

            if data is None:
                continue

            # ---------- 帧推理 ----------
            t0 = time.perf_counter()
            try:
                # 推理放线程池，避免阻塞事件循环影响其他连接
                landmarks = await loop.run_in_executor(None, _infer, data)
            except Exception:
                logger.exception("推理失败")
                await ws.send_json({"type": "error", "message": "推理失败"})
                continue

            if not landmarks:
                await ws.send_json({"type": "result", "error": "no_person"})
                continue

            smoothed = smoother.smooth(landmarks)
            angles = calculate_angles(smoothed)
            scored = score_pose(smoothed)

            result: dict = {
                "type": "result",
                "landmarks": smoothed,
                "angles": angles,
                "score": scored["score"],
                "suggestions": scored["suggestions"],
                "inference_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

            # ---------- 课程模式：关键帧跟踪 ----------
            if course_session:
                # -1（不可见）不参与匹配，直接复用五要领评分的角度
                course = course_session.update(angles)
                result.update(course)
                if course["deviations"]:
                    result["suggestions"] = [d["text"] for d in course["deviations"]]

            await ws.send_json(result)
    except WebSocketDisconnect:
        pass
    finally:
        logger.info("训练连接断开: %s", payload.get("username"))
