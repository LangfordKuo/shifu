"""FastAPI 入口：uvicorn app.main:app --port 8000"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import APP_NAME, APP_VERSION
from app.api import health, train_ws
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=APP_NAME, version=APP_VERSION)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(train_ws.router)


@app.on_event("startup")
async def preload_model() -> None:
    """后台线程预热 YOLO 模型，避免用户首帧等待数秒。"""
    import threading

    def _load():
        try:
            from app.engine.pose_engine import get_pose_engine

            get_pose_engine()
        except Exception:
            import logging

            logging.getLogger("shifu.ai").exception("模型预热失败（将在首帧重试）")

    threading.Thread(target=_load, daemon=True, name="model-preload").start()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
