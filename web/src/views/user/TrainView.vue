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
const courseInfo = ref<{ title: string; keyframeCount: number } | null>(null);

const phase = ref<'idle' | 'starting' | 'running'>('idle');
const demoActive = ref(false); // 演示图片结果展示中（隐藏摄像头占位提示）
const noPerson = ref(false);
const soundOn = ref(ttsSupported());
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

// 会话统计（课程模式结束时报给后端）
let sessionStart = 0;
let courseScoreSum = 0;
let courseScoreN = 0;
let maxPhase = 0;
let samples: Array<{ t: number; score: number; match: number; phase: number }> = [];

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
      const loaded = await client.sendAndWait<{ phase_total: number }>(
        { type: 'start_course', courseId },
        'course_loaded',
        15000,
      );
      if (!loaded) throw new Error('课程模型加载失败');
      course.phase = 0;
      course.phaseTotal = loaded.phase_total;
      course.cue = '准备';
      course.progress = 0;
      course.match = 0;
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
    return;
  }
  noPerson.value = false;
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

    if (res.phase_changed) {
      speakNow(res.cue ?? '', soundOn.value);
    } else if (result.suggestions[0]) {
      speak(result.suggestions[0], soundOn.value);
    }
  } else if (result.suggestions[0]) {
    speak(result.suggestions[0], soundOn.value);
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
          <div class="mb-1 text-center text-xl font-semibold text-primary">
            {{ course.cue || '准备开始' }}
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-muted">
            <div
              class="h-full rounded-full bg-primary transition-all duration-300"
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
