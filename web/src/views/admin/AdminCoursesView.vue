<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import {
  CloudUpload,
  Film,
  Loader2,
  Plus,
  Rocket,
  Trash2,
  Undo2,
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
    toast.success('课程已创建，AI 正在提取动作模型');
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

function fmtDuration(ms: number) {
  if (!ms) return '—';
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}分${s % 60}秒`;
}

function fmtTime(s: string) {
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

const statusBadge = (s: string) =>
  s === 'PUBLISHED'
    ? { text: '已发布', cls: 'default' as const }
    : s === 'TRAINING'
      ? { text: '提取中', cls: 'secondary' as const }
      : s === 'OFFLINE'
        ? { text: '已下架', cls: 'destructive' as const }
        : { text: '草稿', cls: 'outline' as const };
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
                <Badge :variant="statusBadge(row.status).cls">{{ statusBadge(row.status).text }}</Badge>
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
            上传教练示范视频，AI 将提取关键帧生成动作模型（约每分钟视频耗时 1-2 分钟）
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
              {{ submitting ? '提交中…' : '创建并开始提取' }}
            </Button>
          </DialogFooter>
        </form>
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
