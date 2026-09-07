<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import {
  Camera,
  CameraOff,
  Image as ImageIcon,
  Mic,
  MicOff,
  Play,
  Square,
} from 'lucide-vue-next';
import { toast } from 'vue-sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { drawSkeleton } from '@/lib/skeleton';
import { api, loadTokens } from '@/lib/api';
import { speak, speakNow, stopSpeaking, ttsSupported } from '@/lib/tts';
import {
  TrainClient,
  type ScoreItem,
  type TrainResult,
} from '@/lib/trainClient';

// ---------- 常量 ----------
const TARGET_FPS = 12; // 目标帧率（受 AI 推理速度限制，取实际完成帧数）
const ANGLE_LABELS: Array<[string, string]> = [
  ['left_elbow', '左肘'],
  ['right_elbow', '右肘'],
  ['left_shoulder', '左肩'],
  ['right_shoulder', '右肩'],
  ['left_hip', '左髋'],
  ['right_hip', '右髋'],
  ['left_knee', '左膝'],
  ['right_knee', '右膝'],
];

// ---------- 状态 ----------
const route = useRoute();
const courseId = Number(route.query.course) || null;
const courseInfo = ref<{ title: string; keyframeCount: number; videoUrl?: string | null } | null>(
  null,
);

const phase = ref<'idle' | 'starting' | 'running'>('idle');
const demoActive = ref(false); // 演示图片结果展示中（隐藏摄像头占位提示）
const noPerson = ref(false);
const soundOn = ref(ttsSupported());
const showGhost = ref(true); // 标准骨架贴身对比
const showDemoVideo = ref(true); // 教练示范视频小窗
const ghostPose = ref<Array<{ x: number; y: number; v: number }> | null>(null);
const wsMsg = ref('');
const fps = ref(0);
const latency = ref(0);
const inferenceMs = ref(0);

const videoRef = ref<HTMLVideoElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

const result = reactive({
  score: 0,
  angles: {} as Record<string, number>,
  items: [] as ScoreItem[],
  suggestions: [] as string[],
});

// 课程训练状态
const course = reactive({
  phase: 0,
  phaseTotal: 0,
  cue: '',
  progress: 0,
  match: 0,
});
const holdRemaining = ref<number | null>(null); // 达标后等待进入下一拍的剩余毫秒
// 完成后等待秒数与达标线（本地记住，训练中可调）
const waitSec = ref(Math.min(30, Math.max(0, Number(localStorage.getItem('shifu.waitSec')) || 3)));
const holdTh = ref(Math.min(95, Math.max(50, Number(localStorage.getItem('shifu.holdTh')) || 75)));

// 教练示范视频分段同步：进入第 N 拍 → 播放上一拍标记到本拍标记的片段 → 定格在本拍标准动作
const demoVideoRef = ref<HTMLVideoElement | null>(null);
const keyframeTimes = ref<number[]>([]); // 各拍时间点（ms）
let demoEndMs: number | null = null; // 当前片段结束点（null = 已定格）

// 会话统计（课程模式结束时报给后端）
let sessionStart = 0;
let courseScoreSum = 0;
let courseScoreN = 0;
let maxPhase = 0;
let samples: Array<{ t: number; score: number; match: number; phase: number }> = [];

// ---------- 人性化播报状态 ----------
const jointLastSpoken = new Map<string, number>(); // 每个关节的纠偏冷却
let lastAnyAdviceAt = 0; // 全局纠偏冷却
let lastPraiseAt = 0; // 鼓励冷却
let noPersonFrames = 0; // 连续未检测到人体的帧数
let lastAbsentHintAt = 0; // 离场提示冷却
let praiseIndex = 0;

const PRAISES = ['很好，保持这个姿态', '不错，就是这样', '姿态很标准，继续', '棒，就是这个感觉'];

function resetVoiceState() {
  jointLastSpoken.clear();
  lastAnyAdviceAt = 0;
  lastPraiseAt = 0;
  noPersonFrames = 0;
}

let client: TrainClient | null = null;
let stream: MediaStream | null = null;
let running = false;
let demoImg: HTMLImageElement | null = null;
let fpsCount = 0;
let fpsTimer: number | null = null;

const circ = 2 * Math.PI * 52;
const scoreOffset = computed(() => circ * (1 - result.score / 100));

function scoreColor(s: number) {
  if (s >= 85) return '#3fb950';
  if (s >= 70) return '#d29922';
  return '#e74c3c';
}
function scoreText(s: number) {
  if (s >= 90) return '优秀';
  if (s >= 80) return '良好';
  if (s >= 70) return '合格';
  return '需调整';
}
function angleText(key: string) {
  const v = result.angles[key];
  return v === undefined || v < 0 ? '—' : `${v.toFixed(0)}°`;
}

// ---------- 课程信息预取 ----------
onMounted(async () => {
  if (!courseId) return;
  try {
    courseInfo.value = await api.get(`/courses/${courseId}`);
  } catch {
    toast.error('课程加载失败，已切换为自由训练');
  }
});

// ---------- 启动 / 停止 ----------
async function startTraining() {
  if (phase.value !== 'idle') return;
  if (!loadTokens()?.accessToken) {
    toast.error('请先登录');
    return;
  }
  phase.value = 'starting';
  try {
    demoActive.value = false;
    // 1. 开摄像头
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' },
    });
    const video = videoRef.value!;
    video.srcObject = stream;
    await new Promise<void>((resolve) => {
      if (video.readyState >= 2) return resolve();
      video.onloadedmetadata = () => resolve();
    });
    const canvas = canvasRef.value!;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // 2. 连接 AI 服务
    client = new TrainClient();
    client.onStatus = (s, msg) => {
      wsMsg.value = msg ?? '';
    };
    const ok = await client.connect();
    if (!ok) {
      throw new Error(wsMsg.value || '无法连接 AI 服务');
    }

    // 3. 课程模式：加载课程模型
    if (courseId && courseInfo.value) {
      const loaded = await client.sendAndWait<{
        phase_total: number;
        waitMs: number;
        keyframeTimes: number[];
      }>(
        { type: 'start_course', courseId, waitMs: waitSec.value * 1000, holdTh: holdTh.value },
        'course_loaded',
        15000,
      );
      if (!loaded) throw new Error('课程模型加载失败');
      course.phase = 0;
      course.phaseTotal = loaded.phase_total;
      course.cue = '准备';
      course.progress = 0;
      course.match = 0;
      holdRemaining.value = null;
      keyframeTimes.value = loaded.keyframeTimes ?? [];
      lastSyncedPhase = 0;
      demoEndMs = null;
      resetVoiceState();
      speakNow('准备好，跟随口令开始练习', soundOn.value);
    }

    // 4. 进入推理循环
    running = true;
    phase.value = 'running';
    noPerson.value = false;
    fpsCount = 0;
    sessionStart = Date.now();
    courseScoreSum = 0;
    courseScoreN = 0;
    maxPhase = 0;
    samples = [];
    void frameLoop();

    fpsTimer = window.setInterval(() => {
      fps.value = fpsCount;
      fpsCount = 0;
    }, 1000);
  } catch (err) {
    await stopTraining();
    toast.error(
      err instanceof Error
        ? err.message === 'Not allowed' || err instanceof DOMException
          ? '无法访问摄像头，请检查浏览器权限'
          : err.message
        : '启动失败',
    );
    phase.value = 'idle';
  }
}


async function stopTraining() {
  const hadCourseRun = courseId && courseScoreN > 0;
  const courseSamples = courseId ? samples.splice(0, samples.length) : [];
  running = false;
  phase.value = 'idle';
  demoActive.value = false;
  if (fpsTimer) {
    clearInterval(fpsTimer);
    fpsTimer = null;
  }
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
  if (videoRef.value) videoRef.value.srcObject = null;
  client?.close();
  client = null;
  stopSpeaking();

  // 课程模式：生成训练报告并上报会话
  if (hadCourseRun) {
    const avg = courseScoreSum / courseScoreN;
    const durationMs = Math.min(Date.now() - sessionStart, 86_400_000);
    void (async () => {
      let report: Record<string, unknown> | undefined;
      try {
        // AI 服务生成节奏对齐报告（失败则仅记录基础数据）
        const tokens = loadTokens();
        const resp = await fetch('/ai/api/report', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(tokens?.accessToken ? { Authorization: `Bearer ${tokens.accessToken}` } : {}),
          },
          body: JSON.stringify({
            course_id: courseId,
            samples: courseSamples.slice(0, 2000),
          }),
        });
        if (resp.ok) report = await resp.json();
      } catch {
        // 报告生成失败不阻塞记录
      }
      try {
        await api.post('/training/sessions', {
          courseId,
          score: (report?.overall as number) ?? Number(avg.toFixed(1)),
          durationMs,
          report: report ?? { frames: courseScoreN, phases: maxPhase, phaseTotal: course.phaseTotal },
        });
        toast.success(
          report ? `训练完成，得分 ${report.overall}，报告已生成` : '训练已记录',
        );
      } catch {
        toast.error('训练记录保存失败');
      }
    })();
  }

  const canvas = canvasRef.value;
  canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
  result.score = 0;
  result.items = [];
  result.suggestions = [];
  result.angles = {};
  course.phase = 0;
  course.cue = '';
  course.progress = 0;
  ghostPose.value = null;
  holdRemaining.value = null;
  resetVoiceState();
  lastSyncedPhase = 0;
  demoEndMs = null;
  fps.value = 0;
  latency.value = 0;
}

onBeforeUnmount(() => {
  void stopTraining();
});

// ---------- 推理循环 ----------
async function frameLoop() {
  while (running && client) {
    const t0 = performance.now();
    const jpeg = await captureJpeg();
    if (!running) break;
    if (jpeg) {
      const res = await client.sendFrame(jpeg);
      if (!running) break;
      if (res) {
        latency.value = Math.round(performance.now() - t0);
        handleResult(res);
      }
    }
    const elapsed = performance.now() - t0;
    await sleep(Math.max(0, 1000 / TARGET_FPS - elapsed));
  }
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 截取当前视频帧为 JPEG（demo 模式则取演示图片） */
async function captureJpeg(): Promise<ArrayBuffer | null> {
  const canvas = document.createElement('canvas');
  const video = videoRef.value;
  if (video && video.videoWidth) {
    const scale = Math.min(1, 640 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height);
  } else if (demoImg) {
    const scale = Math.min(1, 640 / demoImg.naturalWidth);
    canvas.width = Math.round(demoImg.naturalWidth * scale);
    canvas.height = Math.round(demoImg.naturalHeight * scale);
    canvas.getContext('2d')!.drawImage(demoImg, 0, 0, canvas.width, canvas.height);
  } else {
    return null;
  }
  return new Promise((resolve) => {
    canvas.toBlob(
      async (blob) => resolve(blob ? await blob.arrayBuffer() : null),
      'image/jpeg',
      0.6,
    );
  });
}

// ---------- 结果处理 ----------
function handleResult(res: TrainResult) {
  if (res.error) {
    noPerson.value = res.error === 'no_person';
    if (noPerson.value && running) {
      noPersonFrames += 1;
      // 离开画面约 1 秒后提示一次，15 秒内不重复唠叨
      if (noPersonFrames === 10 && Date.now() - lastAbsentHintAt > 15_000) {
        lastAbsentHintAt = Date.now();
        speakNow('请回到画面中央，让镜头看到你的全身', soundOn.value);
      }
    }
    return;
  }
  noPerson.value = false;
  noPersonFrames = 0;
  fpsCount += 1;
  inferenceMs.value = res.inference_ms ?? 0;

  if (res.landmarks?.length) {
    const canvas = canvasRef.value;
    if (canvas) {
      if (canvas.width === 0) {
        canvas.width = 640;
        canvas.height = 480;
      }
      // 无摄像头（演示模式）时把演示图作为画布背景
      drawSkeleton(canvas, res.landmarks, {
        background: stream ? null : demoImg,
        // 标准骨架贴身对比（仅真实摄像头时叠加）
        ghost: stream && showGhost.value ? res.ghost ?? null : null,
      });
    }
  }

  result.score = res.score ?? 0;
  result.angles = res.angles ?? {};
  result.items = res.items ?? [];
  result.suggestions = res.suggestions ?? [];

  // 课程模式：阶段进度与口令
  if (typeof res.phase === 'number') {
    course.phase = res.phase;
    course.phaseTotal = res.phase_total ?? course.phaseTotal;
    course.cue = res.cue ?? course.cue;
    course.progress = res.progress ?? course.progress;
    course.match = res.match_score ?? course.match;
    ghostPose.value = res.ghost ?? ghostPose.value;
    holdRemaining.value = res.hold_remaining_ms ?? null;
    // 仅真实摄像头训练计入会话统计（演示图片不计入）
    if (running) {
      // 综合分 = 动作规范(五要领) 与 关键帧匹配 各半
      courseScoreSum += (res.score ?? 0) * 0.5 + (res.match_score ?? 0) * 0.5;
      courseScoreN += 1;
      if (res.phase > maxPhase) maxPhase = res.phase;
      // 采集逐帧样本用于训练报告
      samples.push({
        t: Date.now() - sessionStart,
        score: res.score ?? 0,
        match: res.match_score ?? 0,
        phase: res.phase,
      });
    }

    humanizedSpeak(res);

    // 示范视频分段同步：拍号变化时播放对应片段
    if (res.phase && res.phase !== lastSyncedPhase) {
      lastSyncedPhase = res.phase;
      syncDemoVideo(res.phase);
    }
  } else if (result.suggestions[0]) {
    speak(result.suggestions[0], soundOn.value);
  }
}

/** 人性化语音策略：口令打断播报；达标播保持提示；纠偏按关节冷却、去数字口语化 */
function humanizedSpeak(res: TrainResult) {
  if (!soundOn.value) return;
  const now = Date.now();

  // 1. 阶段切换：打断当前语音播报新口令；最后一拍说完成语
  if (res.phase_changed) {
    if (res.finished) {
      speakNow('整套动作完成，做得漂亮！', soundOn.value);
    } else {
      speakNow(res.cue ?? '', soundOn.value);
    }
    return;
  }

  // 2. 当前拍首次达标：肯定 + 提示保持
  if (res.hold_done) {
    speak('很好，保持住', soundOn.value);
    return;
  }

  // 3. 纠偏：挑最严重的、且该关节 12 秒内没提醒过的；全局至少间隔 4 秒
  const deviation = (res.deviations ?? []).find(
    (d) => now - (jointLastSpoken.get(d.joint) ?? 0) > 12_000,
  );
  if (deviation) {
    if (now - lastAnyAdviceAt >= 4_000) {
      speak(deviation.spoken ?? deviation.text, soundOn.value);
      jointLastSpoken.set(deviation.joint, now);
      lastAnyAdviceAt = now;
    }
    return;
  }

  // 4. 姿态达标且无偏差：低频随机鼓励
  if (res.all_good && now - lastPraiseAt > 20_000 && now - lastAnyAdviceAt > 6_000) {
    speak(PRAISES[praiseIndex % PRAISES.length]!, soundOn.value);
    praiseIndex += 1;
    lastPraiseAt = now;
    lastAnyAdviceAt = now;
  }
}

// ---------- 等待时长设置与跳过 ----------
function onWaitChange() {
  waitSec.value = Math.min(30, Math.max(0, Math.round(Number(waitSec.value) || 0)));
  localStorage.setItem('shifu.waitSec', String(waitSec.value));
  client?.sendControl({ type: 'set_wait', waitMs: waitSec.value * 1000 });
  toast.info(`动作完成后将等待 ${waitSec.value} 秒进入下一拍`);
}

function onHoldThChange() {
  holdTh.value = Math.min(95, Math.max(50, Math.round(Number(holdTh.value) || 75)));
  localStorage.setItem('shifu.holdTh', String(holdTh.value));
  client?.sendControl({ type: 'set_hold_th', holdTh: holdTh.value });
  toast.info(`达标线已调整为匹配分 ${holdTh.value} 分`);
}

function skipPhase() {
  if (phase.value !== 'running') return;
  client?.sendControl({ type: 'skip_phase' });
  holdRemaining.value = null;
}

// ---------- 示范视频分段同步 ----------
let lastSyncedPhase = 0;

/** 进入第 p 拍：播放上一拍标记 → 本拍标记 的片段 */
function syncDemoVideo(p: number) {
  const v = demoVideoRef.value;
  if (!v || !keyframeTimes.value.length || !showDemoVideo.value) return;
  const endMs = keyframeTimes.value[p - 1] ?? v.duration * 1000;
  const startMs = p >= 2 ? keyframeTimes.value[p - 2] ?? 0 : 0;
  demoEndMs = endMs;
  try {
    v.currentTime = startMs / 1000;
    void v.play().catch(() => {});
  } catch {
    // 视频未就绪，忽略
  }
}

/** 片段播完：定格在本拍标准动作帧 */
function onDemoTimeUpdate() {
  const v = demoVideoRef.value;
  if (!v || demoEndMs == null) return;
  if (v.currentTime * 1000 >= demoEndMs) {
    v.currentTime = demoEndMs / 1000;
    v.pause();
    demoEndMs = null;
  }
}

/** 开关示范视频小窗：打开时同步到当前拍片段 */
function toggleDemoVideo() {
  showDemoVideo.value = !showDemoVideo.value;
  if (showDemoVideo.value) {
    setTimeout(() => syncDemoVideo(course.phase), 120);
  }
}

// ---------- 演示图片 ----------
async function runDemo() {
  if (phase.value === 'running') return;
  if (!loadTokens()?.accessToken) {
    toast.error('请先登录');
    return;
  }
  phase.value = 'starting';
  try {
    if (!demoImg) {
      demoImg = new Image();
      demoImg.src = '/demo-pose.png';
      await new Promise((resolve, reject) => {
        demoImg!.onload = resolve;
        demoImg!.onerror = reject;
      });
    }
    const canvas = canvasRef.value!;
    const scale = Math.min(1, 1280 / demoImg.naturalWidth);
    canvas.width = Math.round(demoImg.naturalWidth * scale);
    canvas.height = Math.round(demoImg.naturalHeight * scale);
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(demoImg, 0, 0, canvas.width, canvas.height);
    demoActive.value = true;

    if (!client) {
      client = new TrainClient();
      client.onStatus = (s, msg) => {
        wsMsg.value = msg ?? '';
      };
      const ok = await client.connect();
      if (!ok) throw new Error(wsMsg.value || '无法连接 AI 服务');
    }
    if (courseId && courseInfo.value) {
      const loaded = await client.sendAndWait<{ phase_total: number }>(
        { type: 'start_course', courseId },
        'course_loaded',
        15000,
      );
      if (!loaded) throw new Error('课程模型加载失败');
      course.phaseTotal = loaded.phase_total;
    }
    const jpeg = await captureJpeg();
    if (jpeg) {
      const res = await client.sendFrame(jpeg);
      if (res) handleResult(res);
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '演示失败');
  } finally {
    phase.value = 'idle';
  }
}
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">开始训练</h1>
        <p class="text-sm text-muted-foreground">
          {{ courseId && courseInfo ? `课程训练 · ${courseInfo.title}` : '自由训练 · 通用五要领评分' }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Badge v-if="phase === 'running'" variant="outline">{{ fps }} FPS</Badge>
        <Badge v-if="phase === 'running'" variant="outline">
          延迟 {{ latency }}ms · 推理 {{ inferenceMs }}ms
        </Badge>
        <Badge v-if="noPerson && phase === 'running'" variant="destructive">
          未检测到人体
        </Badge>
        <Button
          variant="outline"
          size="icon"
          :title="soundOn ? '关闭语音' : '开启语音'"
          :disabled="!ttsSupported()"
          @click="
            soundOn = !soundOn;
            if (!soundOn) stopSpeaking();
          "
        >
          <Mic v-if="soundOn" />
          <MicOff v-else />
        </Button>
      </div>
    </div>

    <!-- 课程进度条 -->
    <Card v-if="courseId && courseInfo" class="mb-4 border-primary/40">
      <CardContent class="flex flex-wrap items-center justify-between gap-4 py-4">
        <div>
          <div class="text-xs text-muted-foreground">课程进度</div>
          <div class="text-lg font-bold">
            {{ course.phase || 0 }}
            <span class="text-sm font-normal text-muted-foreground">/ {{ course.phaseTotal || courseInfo.keyframeCount }} 拍</span>
          </div>
        </div>
        <div class="min-w-40 flex-1">
          <div
            class="mb-1 text-center text-xl font-semibold"
            :class="holdRemaining != null ? 'text-green-600' : 'text-primary'"
          >
            <template v-if="holdRemaining != null">
              已达标 · {{ (holdRemaining / 1000).toFixed(1) }}s 后进入下一拍
            </template>
            <template v-else>{{ course.cue || '准备开始' }}</template>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-muted">
            <div
              class="h-full rounded-full transition-all duration-300"
              :class="holdRemaining != null ? 'bg-green-600' : 'bg-primary'"
              :style="{ width: (course.progress || 0) * 100 + '%' }"
            ></div>
          </div>
        </div>
        <div class="text-right">
          <div class="text-xs text-muted-foreground">动作匹配</div>
          <div class="text-lg font-bold" :style="{ color: scoreColor(course.match) }">
            {{ course.match ? course.match.toFixed(0) : '—' }}
          </div>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-4 lg:grid-cols-3">
      <!-- 左：画面 -->
      <div class="space-y-3 lg:col-span-2">
        <Card class="overflow-hidden p-0">
          <div class="relative aspect-video bg-black">
            <div class="absolute inset-0" :class="phase === 'running' ? 'scale-x-[-1]' : ''">
              <video
                ref="videoRef"
                class="h-full w-full object-contain"
                autoplay
                playsinline
                muted
              ></video>
              <canvas ref="canvasRef" class="absolute inset-0 h-full w-full"></canvas>
            </div>

            <!-- 达标大字倒计时（镜像容器外，避免翻转） -->
            <div
              v-if="holdRemaining != null && phase === 'running'"
              class="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-2"
            >
              <div class="text-sm font-medium tracking-widest text-white/90 drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)]">
                动作达标 · 保持住
              </div>
              <div
                class="text-[110px] font-black leading-none text-white drop-shadow-[0_4px_24px_rgba(0,0,0,0.85)] sm:text-[140px]"
              >
                {{ Math.ceil(holdRemaining / 1000) }}
              </div>
            </div>

            <!-- 教练示范视频小窗（镜像容器外，避免左右翻转）：进入第 N 拍时播放上一拍→本拍片段，播完定格在本拍标准动作 -->
            <div
              v-if="showDemoVideo && courseInfo?.videoUrl && phase === 'running'"
              class="absolute right-2 top-2 z-10 w-24 overflow-hidden rounded-lg border border-white/40 shadow-lg sm:w-36"
            >
              <video
                ref="demoVideoRef"
                class="h-auto w-full"
                :src="courseInfo.videoUrl"
                autoplay
                muted
                playsinline
                @timeupdate="onDemoTimeUpdate"
              ></video>
              <div
                class="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] text-white"
              >
                示范 · 第 {{ course.phase || 1 }} 拍
              </div>
            </div>

            <div
              v-if="phase === 'idle' && !demoActive"
              class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/70"
            >
              <Camera class="size-10" />
              <p class="text-sm">点击「开始训练」开启摄像头</p>
              <p class="text-xs">没有摄像头？试试「演示图片」体验完整流程</p>
            </div>
            <div
              v-if="phase === 'starting'"
              class="absolute inset-0 flex items-center justify-center bg-black/60 text-sm text-white"
            >
              正在连接 AI 服务…
            </div>
          </div>
        </Card>

        <div class="flex flex-wrap gap-2">
          <Button v-if="phase !== 'running'" :disabled="phase === 'starting'" @click="startTraining">
            <Play />
            开始训练
          </Button>
          <Button v-else variant="destructive" @click="stopTraining">
            <Square />
            停止训练
          </Button>
          <Button variant="outline" :disabled="phase !== 'idle'" @click="runDemo">
            <ImageIcon />
            演示图片
          </Button>
          <Button
            v-if="courseId"
            size="sm"
            :variant="showGhost ? 'secondary' : 'outline'"
            :title="showGhost ? '关闭标准骨架对比' : '开启标准骨架对比'"
            @click="showGhost = !showGhost"
          >
            骨架对比 {{ showGhost ? '开' : '关' }}
          </Button>
          <Button
            v-if="courseId && courseInfo?.videoUrl"
            size="sm"
            :variant="showDemoVideo ? 'secondary' : 'outline'"
            :title="showDemoVideo ? '关闭示范视频' : '开启示范视频'"
            @click="toggleDemoVideo"
          >
            示范视频 {{ showDemoVideo ? '开' : '关' }}
          </Button>
          <div v-if="courseId" class="ml-auto flex items-center gap-1.5 text-sm text-muted-foreground">
            完成后等待
            <Input
              v-model.number="waitSec"
              type="number"
              min="0"
              max="30"
              class="h-8 w-16"
              @change="onWaitChange"
            />
            秒 · 达标线
            <Input
              v-model.number="holdTh"
              type="number"
              min="50"
              max="95"
              class="h-8 w-16"
              title="当前拍匹配分达到该值判定动作完成"
              @change="onHoldThChange"
            />
            分
            <Button size="sm" variant="outline" :disabled="phase !== 'running'" @click="skipPhase">
              跳过此拍
            </Button>
          </div>
        </div>
      </div>

      <!-- 右：实时数据 -->
      <div class="space-y-4">
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-base">实时评分</CardTitle>
          </CardHeader>
          <CardContent class="flex items-center gap-4">
            <div class="relative size-[104px]">
              <svg width="104" height="104" viewBox="0 0 120 120">
                <circle
                  cx="60"
                  cy="60"
                  r="52"
                  fill="none"
                  stroke="var(--muted)"
                  stroke-width="9"
                />
                <circle
                  cx="60"
                  cy="60"
                  r="52"
                  fill="none"
                  :stroke="scoreColor(result.score)"
                  stroke-width="9"
                  stroke-linecap="round"
                  :stroke-dasharray="circ"
                  :stroke-dashoffset="scoreOffset"
                  transform="rotate(-90 60 60)"
                  class="transition-[stroke-dashoffset] duration-500"
                />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center">
                <span class="text-2xl font-bold" :style="{ color: scoreColor(result.score) }">
                  {{ result.score || '—' }}
                </span>
              </div>
            </div>
            <div>
              <div class="text-lg font-semibold" :style="{ color: scoreColor(result.score) }">
                {{ result.score ? scoreText(result.score) : '等待训练' }}
              </div>
              <div class="text-xs text-muted-foreground">
                {{ courseId ? '规范 + 匹配综合评分' : '通用五要领评分' }}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-base">关节角度</CardTitle>
          </CardHeader>
          <CardContent class="grid grid-cols-2 gap-2">
            <div
              v-for="[key, label] in ANGLE_LABELS"
              :key="key"
              class="flex items-center justify-between rounded-md bg-muted/60 px-3 py-1.5 text-sm"
            >
              <span class="text-muted-foreground">{{ label }}</span>
              <span class="font-medium">{{ angleText(key) }}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-base">评分明细</CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <p v-if="result.items.length === 0" class="py-2 text-sm text-muted-foreground">
              开始训练后显示
            </p>
            <div v-for="item in result.items" :key="item.name" class="flex items-center gap-2 text-sm">
              <span class="w-20 shrink-0 text-muted-foreground">{{ item.name }}</span>
              <div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :style="{ width: item.score + '%', background: scoreColor(item.score) }"
                ></div>
              </div>
              <span
                class="w-8 text-right font-semibold"
                :style="{ color: scoreColor(item.score) }"
              >
                {{ item.score }}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="flex items-center gap-2 text-base">
              <Mic class="size-4" />
              纠偏建议
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul class="space-y-1.5">
              <li
                v-for="(s, i) in result.suggestions"
                :key="i"
                class="rounded-md bg-muted/60 px-3 py-1.5 text-sm"
                :class="{ 'text-muted-foreground': s.includes('保持') }"
              >
                {{ s }}
              </li>
              <li v-if="result.suggestions.length === 0" class="py-2 text-sm text-muted-foreground">
                开始训练后显示
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
