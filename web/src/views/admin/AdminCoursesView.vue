<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import {
  CloudUpload,
  Film,
  ListOrdered,
  Loader2,
  MapPinPlus,
  Pause,
  Play,
  Plus,
  Rocket,
  Trash2,
  Undo2,
  Volume2,
  VolumeX,
  Wand2,
} from 'lucide-vue-next';
import { toast } from 'vue-sonner';
import { api } from '@/lib/api';
import { uploadWithProgress } from '@/lib/upload';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface CourseRow {
  id: number;
  title: string;
  description: string | null;
  category: string;
  coverUrl: string | null;
  status: 'DRAFT' | 'TRAINING' | 'PUBLISHED' | 'OFFLINE';
  videoPath: string | null;
  createdAt: string;
  keyframeCount: number;
  durationMs: number;
  job: { id: number; type: string; status: string; progress: number; error: string | null } | null;
}

const CATEGORY_LABELS: Record<string, string> = {
  general: '综合',
  taiji: '太极',
  changquan: '长拳',
  taolu: '套路',
};

const rows = ref<CourseRow[]>([]);
const loading = ref(false);
let pollTimer: number | null = null;

async function load() {
  loading.value = true;
  try {
    const data = await api.get<{ items: CourseRow[] }>('/admin/courses');
    rows.value = data.items;
    schedulePoll();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载课程失败');
  } finally {
    loading.value = false;
  }
}

const hasRunningJob = computed(() =>
  rows.value.some((r) => r.job?.status === 'RUNNING' || r.job?.status === 'PENDING'),
);

function schedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  if (hasRunningJob.value) {
    pollTimer = window.setTimeout(() => {
      api
        .get<{ items: CourseRow[] }>('/admin/courses')
        .then((d) => (rows.value = d.items))
        .catch(() => {})
        .finally(schedulePoll);
    }, 2000);
  }
}

onMounted(load);
onBeforeUnmount(() => pollTimer && clearTimeout(pollTimer));

// ---------- 新建课程 ----------
const dialogOpen = ref(false);
const submitting = ref(false);
const uploadPercent = ref(0);
const videoName = ref('');
const fileInput = ref<HTMLInputElement | null>(null);
const form = reactive({
  title: '',
  description: '',
  category: 'general',
  video: null as File | null,
});

function openCreate() {
  Object.assign(form, { title: '', description: '', category: 'general', video: null });
  videoName.value = '';
  uploadPercent.value = 0;
  dialogOpen.value = true;
}

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (file) {
    form.video = file;
    videoName.value = file.name;
  }
}

async function submit() {
  if (!form.title.trim()) return toast.error('请填写课程标题');
  if (!form.video) return toast.error('请选择示范视频');
  submitting.value = true;
  try {
    const fd = new FormData();
    fd.append('title', form.title.trim());
    if (form.description.trim()) fd.append('description', form.description.trim());
    fd.append('category', form.category);
    fd.append('video', form.video);
    await uploadWithProgress('/api/admin/courses', fd, (p) => (uploadPercent.value = p));
    toast.success('课程已创建，请在列表中点击「打标」标记每一拍');
    dialogOpen.value = false;
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '创建失败');
  } finally {
    submitting.value = false;
  }
}

// ---------- 发布 / 下架 / 删除 ----------
async function publish(row: CourseRow) {
  try {
    await api.patch(`/admin/courses/${row.id}`, { status: 'PUBLISHED' });
    toast.success('已发布');
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '操作失败');
  }
}

async function offline(row: CourseRow) {
  try {
    await api.patch(`/admin/courses/${row.id}`, { status: 'OFFLINE' });
    toast.success('已下架');
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '操作失败');
  }
}

const deleteTarget = ref<CourseRow | null>(null);
const deleteOpen = ref(false);

async function confirmDelete() {
  if (!deleteTarget.value) return;
  try {
    await api.delete(`/admin/courses/${deleteTarget.value.id}`);
    toast.success('课程已删除');
    deleteOpen.value = false;
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除失败');
  }
}

// ---------- 人工打标 ----------
interface MarkerRow {
  tMs: number;
  cue: string;
}
const markDialog = ref(false);
const markCourse = ref<CourseRow | null>(null);
const markers = ref<MarkerRow[]>([]);
const markVideoRef = ref<HTMLVideoElement | null>(null);
const currentTime = ref(0);
const savingMarkers = ref(false);
const generating = ref(false);

// 自绘进度条 / 播放控制
const trackRef = ref<HTMLDivElement | null>(null);
const isPlaying = ref(false);
const isMuted = ref(false);
const durMs = ref(0);
const dragIndex = ref(-1);

const progressPct = computed(() =>
  durMs.value > 0 ? Math.min(100, (currentTime.value * 1000) / durMs.value * 100) : 0,
);

function markerPct(m: MarkerRow) {
  return durMs.value > 0 ? Math.min(100, (m.tMs / durMs.value) * 100) : 0;
}

function onVideoMeta(e: Event) {
  durMs.value = Math.round((e.target as HTMLVideoElement).duration * 1000) || 0;
}

function togglePlay() {
  const v = markVideoRef.value;
  if (!v) return;
  if (v.paused) void v.play();
  else v.pause();
}

function toggleMute() {
  const v = markVideoRef.value;
  if (!v) return;
  v.muted = !v.muted;
  isMuted.value = v.muted;
}

function onTrackSeek(e: PointerEvent) {
  const track = trackRef.value;
  const v = markVideoRef.value;
  if (!track || !v || !durMs.value) return;
  const rect = track.getBoundingClientRect();
  const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
  v.currentTime = (ratio * durMs.value) / 1000;
}

/** 拖动打点圆点微调时间，松手后与相邻打点保持至少 0.2s 间隔 */
function startDrag(i: number, e: PointerEvent) {
  e.preventDefault();
  dragIndex.value = i;
  const track = trackRef.value;
  if (!track) return;
  const rect = track.getBoundingClientRect();

  const move = (ev: PointerEvent) => {
    const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    markers.value[i]!.tMs = Math.round(ratio * durMs.value);
    currentTime.value = markers.value[i]!.tMs / 1000;
  };
  const up = () => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    // 与相邻打点保持最小间隔
    const MIN_GAP = 200;
    const prev = markers.value[i - 1]?.tMs ?? -Infinity;
    const next = markers.value[i + 1]?.tMs ?? Infinity;
    markers.value[i]!.tMs = Math.min(Math.max(markers.value[i]!.tMs, prev + MIN_GAP), next - MIN_GAP);
    dragIndex.value = -1;
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
}

async function openMarking(row: CourseRow) {
  markCourse.value = row;
  markers.value = [];
  markDialog.value = true;
  try {
    const data = await api.get<{ markers: MarkerRow[] }>(
      `/admin/courses/${row.id}/markers`,
    );
    markers.value = data.markers;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载打标失败');
  }
}

function addMarker() {
  const t = Math.round((markVideoRef.value?.currentTime ?? 0) * 1000);
  if (markers.value.some((m) => Math.abs(m.tMs - t) < 200)) {
    toast.warning('距离上一个打点太近（<0.2 秒）');
    return;
  }
  markers.value.push({ tMs: t, cue: '' });
  markers.value.sort((a, b) => a.tMs - b.tMs);
}

function removeMarker(i: number) {
  markers.value.splice(i, 1);
}

function fmtMs(ms: number) {
  const s = ms / 1000;
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toFixed(1).padStart(4, '0')}`;
}

async function saveMarkers(silent = false) {
  if (!markCourse.value) return;
  savingMarkers.value = true;
  try {
    await api.put(`/admin/courses/${markCourse.value.id}/markers`, {
      markers: markers.value,
    });
    if (!silent) toast.success('打标已保存');
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存失败');
    throw err;
  } finally {
    savingMarkers.value = false;
  }
}

async function generateModel() {
  if (markers.value.length === 0) {
    toast.error('请至少打一个点');
    return;
  }
  generating.value = true;
  try {
    await saveMarkers(true);
    await api.post(`/admin/courses/${markCourse.value!.id}/generate-model`);
    toast.success('已开始生成动作模型，可在列表查看进度');
    markDialog.value = false;
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '生成失败');
  } finally {
    generating.value = false;
  }
}

function onGlobalKeydown(e: KeyboardEvent) {
  if (!markDialog.value) return;
  const tag = (e.target as HTMLElement)?.tagName;
  if (e.code === 'Space' && !['INPUT', 'TEXTAREA', 'BUTTON'].includes(tag)) {
    e.preventDefault();
    addMarker();
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown));

async function beforeUnmountCleanup() {
  window.removeEventListener('keydown', onGlobalKeydown);
}
onBeforeUnmount(() => void beforeUnmountCleanup());

function fmtDuration(ms: number) {
  if (!ms) return '—';
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}分${s % 60}秒`;
}

// ---------- 关键帧口令编辑 ----------
interface KeyframeRow {
  index: number;
  tMs: number;
  cue: string;
}
const kfDialog = ref(false);
const kfCourse = ref<CourseRow | null>(null);
const kfRows = ref<KeyframeRow[]>([]);
const kfLoading = ref(false);
const kfSaving = ref(false);

async function openKeyframes(row: CourseRow) {
  kfCourse.value = row;
  kfDialog.value = true;
  kfLoading.value = true;
  try {
    const data = await api.get<{ keyframes: KeyframeRow[] }>(
      `/admin/courses/${row.id}/keyframes`,
    );
    kfRows.value = data.keyframes;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载关键帧失败');
    kfDialog.value = false;
  } finally {
    kfLoading.value = false;
  }
}

async function saveCues() {
  if (!kfCourse.value) return;
  kfSaving.value = true;
  try {
    const res = await api.put<{ updated: number }>(
      `/admin/courses/${kfCourse.value.id}/keyframes/cues`,
      { cues: kfRows.value.map((k) => ({ index: k.index, cue: k.cue })) },
    );
    toast.success(`已更新 ${res.updated} 条口令`);
    kfDialog.value = false;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存失败');
  } finally {
    kfSaving.value = false;
  }
}

function fmtTime(s: string) {
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

const statusBadge = (s: string, keyframes = 1) =>
  s === 'PUBLISHED'
    ? { text: '已发布', cls: 'default' as const }
    : s === 'TRAINING'
      ? { text: '生成中', cls: 'secondary' as const }
      : s === 'OFFLINE'
        ? { text: '已下架', cls: 'destructive' as const }
        : keyframes
          ? { text: '草稿', cls: 'outline' as const }
          : { text: '待打标', cls: 'outline' as const };
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">课程管理</h1>
        <p class="text-sm text-muted-foreground">
          上传示范视频，AI 自动提取关键帧生成课程模型
        </p>
      </div>
      <Button @click="openCreate">
        <Plus />
        新建课程
      </Button>
    </div>

    <Card>
      <CardContent class="pt-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>课程</TableHead>
              <TableHead>分类</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>动作模型</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead class="w-40 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-if="rows.length === 0">
              <TableCell colspan="6" class="h-24 text-center text-muted-foreground">
                {{ loading ? '加载中…' : '还没有课程，点击右上角新建' }}
              </TableCell>
            </TableRow>
            <TableRow v-for="row in rows" :key="row.id">
              <TableCell>
                <div class="font-medium">{{ row.title }}</div>
                <div v-if="row.description" class="max-w-xs truncate text-xs text-muted-foreground">
                  {{ row.description }}
                </div>
              </TableCell>
              <TableCell>{{ CATEGORY_LABELS[row.category] ?? row.category }}</TableCell>
              <TableCell>
                <Badge :variant="statusBadge(row.status, row.keyframeCount).cls">
                  {{ statusBadge(row.status, row.keyframeCount).text }}
                </Badge>
                <div v-if="row.job?.status === 'FAILED'" class="mt-1 max-w-40 text-xs text-destructive">
                  {{ row.job.error }}
                </div>
              </TableCell>
              <TableCell>
                <template v-if="row.keyframeCount">
                  {{ row.keyframeCount }} 拍 · {{ fmtDuration(row.durationMs) }}
                </template>
                <div v-else-if="row.job && (row.job.status === 'RUNNING' || row.job.status === 'PENDING')" class="w-28">
                  <div class="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <Loader2 class="size-3 animate-spin" />
                    {{ row.job.progress }}%
                  </div>
                  <div class="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      class="h-full rounded-full bg-primary transition-all"
                      :style="{ width: row.job.progress + '%' }"
                    ></div>
                  </div>
                </div>
                <span v-else class="text-muted-foreground">—</span>
              </TableCell>
              <TableCell class="text-muted-foreground">{{ fmtTime(row.createdAt) }}</TableCell>
              <TableCell class="space-x-1 text-right">
                <Button
                  v-if="row.videoPath"
                  size="sm"
                  variant="ghost"
                  title="视频打标"
                  @click="openMarking(row)"
                >
                  <MapPinPlus />
                </Button>
                <Button
                  v-if="row.keyframeCount"
                  size="sm"
                  variant="ghost"
                  title="编辑关键帧口令"
                  @click="openKeyframes(row)"
                >
                  <ListOrdered />
                </Button>
                <Button
                  v-if="row.status === 'DRAFT' && row.keyframeCount"
                  size="sm"
                  variant="outline"
                  @click="publish(row)"
                >
                  <Rocket />
                  发布
                </Button>
                <Button
                  v-if="row.status === 'PUBLISHED'"
                  size="sm"
                  variant="outline"
                  @click="offline(row)"
                >
                  <Undo2 />
                  下架
                </Button>
                <Button size="sm" variant="ghost" class="text-destructive" @click="deleteTarget = row; deleteOpen = true">
                  <Trash2 />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <!-- 新建课程 -->
    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新建课程</DialogTitle>
          <DialogDescription>
            上传教练示范视频；保存后在课程列表点击「打标」人工标记每一拍，再生成动作模型
          </DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit.prevent="submit">
          <div class="space-y-2">
            <Label for="c-title">课程标题</Label>
            <Input id="c-title" v-model="form.title" placeholder="如：太极八式 · 起势" />
          </div>
          <div class="space-y-2">
            <Label for="c-desc">课程简介</Label>
            <Input id="c-desc" v-model="form.description" placeholder="课程内容说明（可选）" />
          </div>
          <div class="space-y-2">
            <Label>分类</Label>
            <Select v-model="form.category">
              <SelectTrigger class="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="(label, key) in CATEGORY_LABELS" :key="key" :value="key">
                  {{ label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>示范视频</Label>
            <div
              class="flex items-center gap-3 rounded-lg border border-dashed p-4"
              :class="{ 'border-primary': form.video }"
            >
              <Film class="size-6 text-muted-foreground" />
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{{ videoName || '未选择视频' }}</div>
                <div class="text-xs text-muted-foreground">支持 MP4 / MOV / WebM，≤500MB</div>
              </div>
              <Button type="button" variant="outline" size="sm" @click="fileInput?.click()">
                选择文件
              </Button>
              <input ref="fileInput" type="file" accept="video/*" class="hidden" @change="onFileChange" />
            </div>
          </div>
          <div v-if="submitting" class="space-y-1">
            <div class="flex justify-between text-xs text-muted-foreground">
              <span>上传中…</span>
              <span>{{ uploadPercent }}%</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-muted">
              <div
                class="h-full rounded-full bg-primary transition-all"
                :style="{ width: uploadPercent + '%' }"
              ></div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" :disabled="submitting" @click="dialogOpen = false">
              取消
            </Button>
            <Button type="submit" :disabled="submitting">
              <CloudUpload v-if="!submitting" />
              <Loader2 v-else class="animate-spin" />
              {{ submitting ? '提交中…' : '创建课程' }}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <!-- 关键帧口令编辑 -->
    <Dialog v-model:open="kfDialog">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>关键帧口令 · {{ kfCourse?.title }}</DialogTitle>
          <DialogDescription>
            训练到对应拍时 TTS 将播报口令，建议写成动作要领（如"起势，两臂慢慢前举"）
          </DialogDescription>
        </DialogHeader>
        <div v-if="kfLoading" class="py-8 text-center text-sm text-muted-foreground">加载中…</div>
        <div v-else class="max-h-80 space-y-2 overflow-y-auto pr-1">
          <div v-for="k in kfRows" :key="k.index" class="flex items-center gap-3">
            <span class="w-16 shrink-0 text-sm text-muted-foreground">
              第 {{ k.index }} 拍
            </span>
            <span class="w-16 shrink-0 text-xs text-muted-foreground">
              {{ Math.round(k.tMs / 1000) }}s
            </span>
            <Input v-model="k.cue" :placeholder="`第 ${k.index} 拍的动作要领`" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" :disabled="kfSaving" @click="kfDialog = false">取消</Button>
          <Button :disabled="kfSaving || kfLoading" @click="saveCues">
            <Loader2 v-if="kfSaving" class="animate-spin" />
            保存口令
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 视频打标 -->
    <Dialog v-model:open="markDialog">
      <DialogContent class="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>视频打标 · {{ markCourse?.title }}</DialogTitle>
          <DialogDescription>
            播放视频，在每个动作拍的位置「打点」（或按空格键），为每拍填写口令后生成动作模型
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-2">
          <div class="overflow-hidden rounded-lg border bg-black">
            <video
              ref="markVideoRef"
              :src="markCourse?.videoPath ?? undefined"
              class="max-h-[40vh] w-full cursor-pointer"
              playsinline
              @click="togglePlay"
              @timeupdate="currentTime = ($event.target as HTMLVideoElement).currentTime"
              @loadedmetadata="onVideoMeta"
              @play="isPlaying = true"
              @pause="isPlaying = false"
              @ended="isPlaying = false"
            ></video>
          </div>

          <!-- 自绘进度条：打标圆点标注，可点击跳转、拖动圆点微调 -->
          <div
            ref="trackRef"
            class="relative h-3 cursor-pointer select-none rounded-full bg-muted"
            @pointerdown="onTrackSeek"
          >
            <div
              class="absolute inset-y-0 left-0 rounded-full bg-primary/60"
              :style="{ width: progressPct + '%' }"
            ></div>
            <div
              v-for="(m, i) in markers"
              :key="'mk' + m.tMs"
              class="group absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2"
              :style="{ left: markerPct(m) + '%' }"
              :title="`第${i + 1}拍 ${fmtMs(m.tMs)}（拖动调整）`"
              @pointerdown.stop="startDrag(i, $event)"
            >
              <div
                class="size-3.5 rounded-full border-2 border-white bg-amber-400 shadow-md transition-transform group-hover:scale-125"
                :class="dragIndex === i ? 'scale-125 cursor-grabbing ring-2 ring-amber-300' : 'cursor-grab'"
              ></div>
            </div>
            <div
              class="pointer-events-none absolute top-1/2 z-20 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow"
              :style="{ left: progressPct + '%' }"
            ></div>
          </div>

          <!-- 播放控制 -->
          <div class="flex items-center gap-2">
            <Button size="icon" variant="ghost" class="size-8" @click="togglePlay">
              <Pause v-if="isPlaying" class="size-4" />
              <Play v-else class="size-4" />
            </Button>
            <span class="font-mono text-xs text-muted-foreground">
              {{ fmtMs(Math.round(currentTime * 1000)) }} / {{ fmtMs(durMs) }}
            </span>
            <Button size="icon" variant="ghost" class="size-8" @click="toggleMute">
              <Volume2 v-if="!isMuted" class="size-4" />
              <VolumeX v-else class="size-4" />
            </Button>
            <span class="ml-auto text-xs text-muted-foreground">
              点击进度条跳转 · 拖动金色圆点微调打点位置
            </span>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
            <Button size="sm" @click="addMarker">
              <MapPinPlus />
              在当前位置打点（{{ fmtMs(Math.round(currentTime * 1000)) }}）
            </Button>
            <span class="text-xs text-muted-foreground">
              共 {{ markers.length }} 拍 · 播放中按空格键快速打点
            </span>
            <div class="ml-auto flex gap-2">
              <Button
                size="sm"
                variant="outline"
                :disabled="savingMarkers || markers.length === 0"
                @click="saveMarkers()"
              >
                <Loader2 v-if="savingMarkers" class="animate-spin" />
                保存打标
              </Button>
              <Button
                size="sm"
                :disabled="generating || markers.length === 0"
                @click="generateModel"
              >
                <Wand2 />
                生成动作模型
              </Button>
            </div>
          </div>
          <div class="max-h-48 space-y-1.5 overflow-y-auto rounded-lg border p-2">
            <p v-if="markers.length === 0" class="py-6 text-center text-sm text-muted-foreground">
              还没有打点：播放视频到动作拍位置，点击上方按钮打点
            </p>
            <div v-for="(m, i) in markers" :key="m.tMs" class="flex items-center gap-2 text-sm">
              <span class="w-14 shrink-0 font-mono text-xs text-muted-foreground">
                {{ fmtMs(m.tMs) }}
              </span>
              <span class="w-12 shrink-0 text-xs text-muted-foreground">第{{ i + 1 }}拍</span>
              <Input v-model="m.cue" :placeholder="`第 ${i + 1} 拍动作要领（可选）`" class="h-8" />
              <Button
                size="icon"
                variant="ghost"
                class="size-8 shrink-0 text-destructive"
                @click="removeMarker(i)"
              >
                <X class="size-4" />
              </Button>
            </div>
          </div>
      </DialogContent>
    </Dialog>

    <!-- 删除确认 -->
    <Dialog v-model:open="deleteOpen">
      <DialogContent class="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>确认删除</DialogTitle>
          <DialogDescription>
            确定要删除课程「{{ deleteTarget?.title }}」吗？其动作模型与学员训练记录将一并删除。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="deleteOpen = false">取消</Button>
          <Button variant="destructive" @click="confirmDelete">删除</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
