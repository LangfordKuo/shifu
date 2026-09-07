# shifu 系统架构与核心设计

> 版本 v1（M1 落地后定稿），后续按里程碑滚动更新。

## 1. 总体架构

```
┌─────────────────────────── 浏览器 (Vue 3 SPA) ───────────────────────────┐
│  用户端: 概览 / 课程 / 训练页(摄像头+骨架叠加+TTS) / 训练记录              │
│  管理端: 用户权限管理 / 课程管理(上传视频→训练) / 任务状态 / 数据统计      │
└──────────────┬──────────────────────────────┬────────────────────────────┘
        REST /api (JWT)                  WebSocket /ai/ws/train (帧流 + JWT)
┌──────────────▼──────────────┐   ┌───────────────▼───────────────────────┐
│  Node.js (NestJS)  :3000    │   │  Python AI 服务 (FastAPI)  :8000       │
│  · auth   登录/刷新/RBAC    │   │  · /ws/train   实时推理 WS              │
│  · users  用户管理          │   │  · YOLO pose 推理 + 平滑 + 归一化       │
│  · courses 课程管理(M3)     │──►│  · 角度计算 / 评分 / 纠偏建议生成        │
│  · training 训练记录(M3)    │HTTP│  · 视频关键点提取(后台任务)             │
│  · 上传存储 / 静态资源       │回调│  · 课程模型生成(模板法)                 │
│  · SQLite/MySQL (Prisma)    │   │  · 设备自动探测(cuda/cpu)               │
└─────────────────────────────┘   └────────────────────────────────────────┘
```

职责边界：**Node 管"业务与数据"，Python 管"算力与模型"**。Python 服务无状态，
后续上云可独立横向扩容或替换为 GPU 机型。

## 2. 关键设计决策

### 2.1 课程模型 = 模板法（一期） + 深度学习（二期预留）

**一期（模板法，无需 GPU 训练）：**

```
示范视频 ─► YOLO 逐帧关键点 ─► 平滑/归一化 ─► 自动切分关键帧 ─► 课程模型 JSON
                                                                    │
用户实时帧 ─► YOLO 关键点 ─► 与"当前进度关键帧"比对 ─► 超差关节 ─► TTS 建议
                └──────────── DTW 序列对齐 ─► 进度/节奏/总分 ─► 训练报告
```

- 归一化：髋中点为原点、肩髋距离为尺度，消除相机距离与机位差异
- 关键帧切分：按姿态变化速率（相邻帧角度向量距离）找极值点
- 课程模型 JSON（存 `data/models/`，元数据在 `course_models` 表）：
  `{ meta, keyframes: [{ t, pose: 17×3, angles, tolerance, cue_text }], global_rules }`
- 优点：确定性、可解释、CPU 可跑、当天出模型；后续管理端可人工微调关键帧与口令

**二期（预留）：** ST-GCN / LSTM 动作分类，用于招式识别等高级功能。
模型文件走同一 `course_models` 表，`type` 字段区分 template / dnn。

### 2.2 实时训练协议（WebSocket，M2 已落地）

```
客户端 ─► {"type":"auth","token":"<JWT>"}            # 连接后 10s 内必须发送
       ─► {"type":"reset"}                           # 重置平滑器
       ─► 二进制帧 = JPEG 图片（≤640px, q0.6）
服务端 ─► {"type":"auth_ok","username":"..."}
       ─► {"type":"result","landmarks":[17点],"angles":{8关节},
           "score":88.5,"items":[...],"suggestions":["..."],
           "inference_ms":83.1}
       ─► {"type":"result","error":"no_person"}
```

- AI 服务启动时后台线程预热模型（首帧不再等待数秒）
- 推理在线程池执行（`run_in_executor`），不阻塞事件循环，多连接可并发
- JWT 鉴权：共享 JWT_SECRET 模式，PyJWT 本地验签（`verify_sub=False` 兼容历史数字 sub）
- 实测性能（CPU i7 级）：推理 ≈73–83ms/帧，WS 往返 ≈110ms，有效 9–12 FPS
- 前端：12 FPS 目标限速 + 背压（上一帧结果返回后才发下一帧）
- 建议生成节流：同句 8s / 全局 3s 冷却；TTS 用浏览器 Web Speech API 本地合成

### 2.3 评分引擎（五要领，源自参考项目的升级）

| 要领 | 判定（17 关键点版本） |
|---|---|
| 坠肘 | 左右肘夹角（肩-肘-腕）区间评分 |
| 屈膝 | 左右膝夹角（髋-膝-踝）区间评分 |
| 身体中正 | 左右肩 y 差、左右髋 y 差的最大值 |
| 重心稳定 | 髋中点 x 与双踝中点 x 偏移 |
| 松胯 | 左右髋夹角（肩-髋-膝）区间评分 |

角度计算工具见 `ai/app/engine/angles.py`；一期针对单个关键帧超差即报，
二期叠加 DTW 后按阶段给分并生成整段报告（总分 + 分项 + 时间轴）。

### 2.4 关键点源可插拔

YOLO pose 为 COCO 17 点（无手指/脚趾细节）。引擎层抽象了关键点接口，
后期可引入 RTMPose(133点) / MediaPipe 补充细节，评分器按所需关节集合声明依赖。

## 3. 数据模型（server/prisma/schema.prisma）

- `User`（role: ADMIN/USER，status: ACTIVE/DISABLED）
- `RefreshToken`（sha256 哈希存储，可吊销，支持登出/改密/重置后强制下线）
- `Course`（status: DRAFT/TRAINING/PUBLISHED/OFFLINE）
- `CourseModel`（课程模型版本，modelPath 指向 JSON 文件）
- `TrainingJob`（AI 任务进度，Node 下发、Python 回写，管理端轮询/SSE 展示）
- `TrainingSession`（训练会话：score / durationMs / reportJson）

SQLite 不支持 enum，全部用字符串常量（`src/common/constants.ts` 为唯一出处），
切 MySQL 时可平滑升级为 enum。

## 4. 认证与权限

- 登录：`POST /api/auth/login` → accessToken(2h) + refreshToken(7d, 轮换)
- 前端 401 自动刷新一次并重放；刷新失败清 token 跳登录
- RBAC：全局 `JwtAuthGuard` + `RolesGuard`，接口用 `@Public()` / `@Roles()` 声明
- 保护规则：不能禁用/降级自己、不能删除自己、系统至少保留一名活跃管理员

## 5. 部署演进

- 开发期（当前）：Windows 三终端 / 或 `npm run dev:*`
- 云上一期：docker-compose —— nginx(静态+反向代理) / node / python(gpu 可选)，
  数据卷挂 SQLite 与 uploads；配置全部走环境变量，无状态化已预留
- 云上二期：SQLite → MySQL 5.7（改 provider + migrate deploy），
  uploads → 对象存储（MinIO/OSS，`videoPath/coverUrl` 已是 URL 抽象）
- 移动端：Capacitor 包壳复用 Web 代码（首选）；远期原生 + 端侧 ONNX 推理
