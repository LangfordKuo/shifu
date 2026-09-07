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

### 2.1 课程模型 = 人工打标 + 模板法（已落地） + 深度学习（二期预留）

**一期（模板法，无需 GPU 训练；打标采用人工模式）：**

```
管理端上传示范视频（不自动切分）
  └► 管理员在视频预览中人工打标（播放器 + 打点按钮/空格键 + 每拍口令）→ PUT markers
  └► 「生成动作模型」POST /generate-model → Python /api/extract-markers
      └► 按打点时间戳定点提取姿态（打点前后 0.7s 采样取最优帧）
      └► 归一化 + 关节角度模板 + 容差 + 口令 → 课程模型 JSON + 封面
      └► 回调 Node PATCH /api/internal/jobs/:id（进度/结果）→ 落库 course_models

用户训练(start_course) ─► Python 拉取模型 GET /api/internal/courses/:id/model
    └► 每帧：lookahead 窗口内最近关键帧匹配（单调推进，≤6拍跳跃）
    └► 阶段切换 → TTS 口令播报；单关节偏差>15° → 纠偏建议（如"左肘再打开一些（目标约160°，当前120°）"）
    └► 综合分 = 五要领规范分 ×0.5 + 关键帧匹配分 ×0.5；结束上报 TrainingSession
```

- 归一化：髋中点为原点、肩髋距离为尺度，消除相机距离与机位差异
- 打标暂存于 `Course.markersJson`（生成模型前可反复调整）；模型 JSON 存
  `ai/data/models/`，元数据在 `course_models` 表：
  `{ version, duration_ms, keyframes: [{ index, t_ms, pose: 17×3, angles, tolerance, cue }] }`
- 某打点检测不到人体时自动跳过（全部失败则任务报错），模型拍数可能少于打点数
- 服务间鉴权：共享 `INTERNAL_TOKEN`（X-Internal-Token 头）

**二期（预留）：** ST-GCN / LSTM 动作分类，用于招式识别等高级功能；
"AI 建议打点"（速率峰值预填标记，人工确认）也可作为辅助功能加入。
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
- 语音策略（人性化）：
  - 阶段切换打断播报新口令（课程引擎下发声量表 spoken/text 分离：语音短句去数字，屏幕带目标角度）
  - 纠偏按"关节"冷却（同一关节 12 秒不重复）+ 全局 4 秒间隔；说法随机多样化
  - 达标低频鼓励（20 秒一次）；最后一拍播完成语；开始前播准备语
  - 离开画面约 1 秒提示一次"请回到画面中央"（15 秒冷却）
- 教学演示：示范视频画中画小窗（可开关）+ 标准骨架"贴身"叠加
  （关键帧归一化 pose 按学员当前髋中点/躯干长度逆变换，金色 ghost 与学员绿色骨架同屏对比）

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

### 2.5 AI 训练建议（DeepSeek，可配置）

- 配置存储：`SystemConfig` 表（ai.baseUrl / ai.model / ai.apiKey / ai.enabled），
  管理端「AI 设置」页填写；密钥不回传浏览器（仅回显是否已配置）
- 默认接口 `https://api.deepseek.com`，模型 `deepseek-v4-flash`（OpenAI 兼容
  `/chat/completions`；接口地址与模型均可改，便于替换其他兼容服务）
- 流程：会话上报（POST /api/training/sessions）→ Node 后台异步将报告摘要
  （课程/综合/规范/匹配/节奏/分拍明细）发给 LLM → 建议写回 `TrainingSession.advice`
- 失败静默降级：未配置密钥、停用开关或调用失败均不影响训练记录本身；
  历史报告弹窗中未就绪时提供「刷新」
- `POST /admin/ai-config/test` 供管理端一键测试连接

## 3. 数据模型（server/prisma/schema.prisma）

- `User`（role: ADMIN/USER，status: ACTIVE/DISABLED）
- `RefreshToken`（sha256 哈希存储，可吊销，支持登出/改密/重置后强制下线）
- `Course`（status: DRAFT/TRAINING/PUBLISHED/OFFLINE）
- `CourseModel`（课程模型版本，modelPath 指向 JSON 文件）
- `TrainingJob`（AI 任务进度，Node 下发、Python 回写，管理端轮询/SSE 展示）
- `TrainingSession`（训练会话：score / durationMs / reportJson / advice）
- `SystemConfig`（键值配置：AI 接口地址 / 模型 / 密钥 / 启用开关）

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
