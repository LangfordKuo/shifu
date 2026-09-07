# shifu · AI 武术动作指导平台

通过 AI 动作识别实现实时的武术动作指导。学员选择课程、打开摄像头开始训练，
系统实时识别骨骼关键点、评估动作质量，并通过 TTS 语音实时播报纠正建议；
管理员负责用户权限管理，上传示范视频即可一键生成课程模型供学员训练。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Tailwind CSS v4 + [shadcn-vue](https://www.shadcn-vue.com/) + Pinia |
| 业务后端 | Node.js + NestJS + Prisma（SQLite 起步，可切 MySQL 5.7） |
| AI 服务 | Python 3.12 + FastAPI + Ultralytics YOLO pose（M2 接入）+ WebSocket |
| 实时语音 | 浏览器 Web Speech API（主）+ 服务端 edge-tts 短语缓存（备） |

## 目录结构

```
shifu/
├── web/      # Vue 3 前端（用户端 + 管理端，同一 SPA 按角色路由）
├── server/   # NestJS 业务服务（认证 / 用户 / 课程 / 训练记录）
├── ai/       # Python AI 服务（WS 实时推理 / 视频提取 / 课程模型）
└── docs/     # 架构与设计文档
```

## 快速开始（Windows 开发机）

前置：Node.js ≥ 20、Python ≥ 3.11（已含 venv）。

```bash
# 1. 安装 Node 依赖（根目录一次性装好 server + web）
npm install

# 2. 初始化数据库并写入种子账号
cd server
npx prisma migrate dev
npx prisma db seed
cd ..

# 3. 初始化 Python AI 服务虚拟环境（首次）
cd ai
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
cd ..

# 4. 启动三个服务（分别开三个终端）
npm run dev:server          # NestJS  -> http://localhost:3000/api
npm run dev:web             # Vite    -> http://localhost:5173（从这里访问）
cd ai && .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

浏览器打开 **http://localhost:5173**。

种子账号（首次登录后请修改密码）：

| 账号 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | 管理员 |
| user1 | 123456 | 学员 |

### GPU 加速（M2 起）

本机有 NVIDIA 显卡时，安装 CUDA 版 torch 即自动启用：

```bash
cd ai
.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

AI 服务启动时自动探测（`/ai/api/health` 的 `device` 字段：cuda / cpu）。

## 服务与代理拓扑

开发时浏览器只访问 Vite（5173），跨服务请求由 Vite 代理：

```
浏览器 ──► Vite :5173
             ├── /api/*  ──►  NestJS :3000   （登录 / 用户 / 课程 / 记录）
             └── /ai/*   ──►  FastAPI :8000  （/ai/ws/train 实时帧流 WS）
```

生产部署时由 nginx 承担同样的路由（见 docs/architecture.md 的部署一节）。

## 数据库与迁移到 MySQL

SQLite 已通过 Prisma 抽象，切换 MySQL 5.7 只需两步：

1. `server/prisma/schema.prisma`：`provider = "sqlite"` 改为 `"mysql"`
2. `server/.env`：`DATABASE_URL="mysql://user:pass@host:3306/shifu"`

然后 `npx prisma migrate deploy`。注意：模型里日期/角色均使用通用类型
（字符串常量代替 enum），不依赖 SQLite 特有语法。

## 路线图

- [x] **M1 基础骨架**：monorepo、JWT 认证 + RBAC、用户管理、前端登录/管理页、AI 服务骨架
- [x] **M2 AI 实时核心**：YOLO26-pose 推理接入 WS、骨架叠加、五要领评分、TTS 语音纠偏、演示图片模式
- [x] **M3 课程体系**：视频上传→AI 提取关键帧→课程模型、课程发布/选课、阶段口令跟踪、训练记录
- [ ] **M4 体验完善**：DTW 整段对齐报告、关键帧口令编辑、管理端统计看板
- [ ] **M5 部署 + 移动端**：docker-compose 上云、Capacitor 打包手机 APP

## 相关文档

- [docs/architecture.md](docs/architecture.md) — 系统架构与核心设计（课程模型 / 评分引擎 / 实时协议）
