"""实时训练 WebSocket：JWT 鉴权 + 帧推理 + 五要领评分 + 建议下发。

协议：
  客户端 -> 服务端:
    {"type": "auth", "token": "<JWT>"}          连接后 10s 内必须发送
    {"type": "reset"}                            重置平滑器（重新开始训练时）
    {"type": "ping"}
    二进制帧 = JPEG 图片
  服务端 -> 客户端:
    {"type": "auth_ok", "username": "..."}
    {"type": "result", "landmarks": [...], "angles": {...},
     "score": 88.5, "items": [...], "suggestions": [...],
     "inference_ms": 21.3}
    {"type": "result", "error": "no_person"}     画面中无人
    {"type": "pong"}
    {"type": "error", "message": "..."}
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
from app.engine.pose_engine import get_pose_engine
from app.engine.scorer import score_pose
from app.engine.smoother import KeypointSmoother

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
        # verify_sub=False：兼容历史签发的数字 sub（RFC 新格式为字符串，签名始终强校验）
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

            if data is not None:
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

                await ws.send_json(
                    {
                        "type": "result",
                        "landmarks": smoothed,
                        "angles": angles,
                        "score": scored["score"],
                        "items": scored["items"],
                        "suggestions": scored["suggestions"],
                        "inference_ms": round((time.perf_counter() - t0) * 1000, 1),
                    }
                )
            elif text is not None:
                try:
                    ctrl = json.loads(text)
                except json.JSONDecodeError:
                    continue
                ctype = ctrl.get("type")
                if ctype == "reset":
                    smoother.reset()
                    await ws.send_json({"type": "reset_ok"})
                elif ctype == "ping":
                    await ws.send_json({"type": "pong", "ts": int(time.time() * 1000)})
    except WebSocketDisconnect:
        pass
    finally:
        logger.info("训练连接断开: %s", payload.get("username"))
