<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { Loader2, Sparkles } from 'lucide-vue-next';
import { toast } from 'vue-sonner';
import { api } from '@/lib/api';
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
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface PhaseDetail {
  phase: number;
  cue: string;
  match: number | null;
  form: number | null;
  duration_ms: number;
  reference_ms: number;
  arrive_ms: number | null;
  practiced: boolean;
}

interface SessionRow {
  id: number;
  courseId: number;
  score: number | null;
  durationMs: number;
  reportJson: string | null;
  advice: string | null;
  createdAt: string;
  course: { title: string };
}

interface Report {
  overall?: number;
  form?: number;
  match?: number | null;
  rhythm?: number | null;
  coverage?: number;
  phases_practiced?: number;
  phase_total?: number;
  duration_ms?: number;
  phase_details?: PhaseDetail[];
}

const rows = ref<SessionRow[]>([]);
const loading = ref(true);
const detail = ref<SessionRow | null>(null);
const detailOpen = ref(false);
const report = ref<Report | null>(null);
const adviceLoading = ref(false);

/** 建议异步生成，刚结束的训练可能还没就绪，可手动刷新 */
async function refreshAdvice() {
  if (!detail.value) return;
  adviceLoading.value = true;
  try {
    const rowsNow = await api.get<SessionRow[]>('/training/sessions/mine');
    rows.value = rowsNow;
    const fresh = rowsNow.find((r) => r.id === detail.value!.id);
    if (fresh) detail.value = fresh;
  } catch {
    /* 静默 */
  } finally {
    adviceLoading.value = false;
  }
}

onMounted(async () => {
  try {
    rows.value = await api.get<SessionRow[]>('/training/sessions/mine');
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载训练记录失败');
  } finally {
    loading.value = false;
  }
});

function scoreColor(s: number) {
  if (s >= 85) return '#3fb950';
  if (s >= 70) return '#d29922';
  return '#e74c3c';
}

function fmtDuration(ms: number) {
  const s = Math.round(ms / 1000);
  return s >= 60 ? `${Math.floor(s / 60)}分${s % 60}秒` : `${s}秒`;
}

function fmtTime(s: string) {
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

function phaseInfo(json: string | null) {
  if (!json) return null;
  try {
    const r = JSON.parse(json) as {
      phases?: number;
      phaseTotal?: number;
      phase_total?: number;
      phases_practiced?: number;
    };
    const done = r.phases ?? r.phases_practiced;
    const total = r.phaseTotal ?? r.phase_total;
    return done != null && total ? `${done}/${total} 拍` : null;
  } catch {
    return null;
  }
}

function openDetail(row: SessionRow) {
  detail.value = row;
  report.value = null;
  if (row.reportJson) {
    try {
      const parsed = JSON.parse(row.reportJson) as Report;
      if (parsed.phase_details) report.value = parsed;
    } catch {
      /* 旧格式报告 */
    }
  }
  detailOpen.value = true;
}
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold">训练记录</h1>
      <p class="text-sm text-muted-foreground">点击记录查看节奏对齐与分拍报告</p>
    </div>

    <Card>
      <CardContent class="pt-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead>
              <TableHead>课程</TableHead>
              <TableHead>得分</TableHead>
              <TableHead>完成度</TableHead>
              <TableHead>时长</TableHead>
              <TableHead class="w-20 text-right">报告</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-if="rows.length === 0">
              <TableCell colspan="6" class="h-24 text-center text-muted-foreground">
                {{ loading ? '加载中…' : '还没有训练记录，去上一堂课吧' }}
              </TableCell>
            </TableRow>
            <TableRow v-for="row in rows" :key="row.id" class="cursor-pointer" @click="openDetail(row)">
              <TableCell class="text-muted-foreground">{{ fmtTime(row.createdAt) }}</TableCell>
              <TableCell class="font-medium">{{ row.course?.title ?? '—' }}</TableCell>
              <TableCell>
                <Badge
                  v-if="row.score != null"
                  :style="{ color: scoreColor(row.score), borderColor: scoreColor(row.score) }"
                  variant="outline"
                >
                  {{ row.score.toFixed(1) }}
                </Badge>
                <span v-else>—</span>
              </TableCell>
              <TableCell>{{ phaseInfo(row.reportJson) ?? '—' }}</TableCell>
              <TableCell class="text-muted-foreground">{{ fmtDuration(row.durationMs) }}</TableCell>
              <TableCell class="text-right">
                <Button v-if="row.reportJson" variant="ghost" size="sm">查看</Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <!-- 报告详情 -->
    <Dialog v-model:open="detailOpen">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>训练报告 · {{ detail?.course?.title }}</DialogTitle>
          <DialogDescription v-if="detail">
            {{ fmtTime(detail.createdAt) }} · 训练时长 {{ fmtDuration(detail.durationMs) }}
          </DialogDescription>
        </DialogHeader>

        <template v-if="report">
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div class="rounded-lg bg-muted/60 p-3 text-center">
              <div class="text-xl font-bold" :style="{ color: scoreColor(report.overall ?? 0) }">
                {{ report.overall }}
              </div>
              <div class="text-xs text-muted-foreground">综合</div>
            </div>
            <div class="rounded-lg bg-muted/60 p-3 text-center">
              <div class="text-xl font-bold" :style="{ color: scoreColor(report.form ?? 0) }">
                {{ report.form }}
              </div>
              <div class="text-xs text-muted-foreground">动作规范</div>
            </div>
            <div class="rounded-lg bg-muted/60 p-3 text-center">
              <div class="text-xl font-bold" :style="{ color: scoreColor(report.match ?? 0) }">
                {{ report.match ?? '—' }}
              </div>
              <div class="text-xs text-muted-foreground">关键帧匹配</div>
            </div>
            <div class="rounded-lg bg-muted/60 p-3 text-center">
              <div class="text-xl font-bold" :style="{ color: scoreColor(report.rhythm ?? 0) }">
                {{ report.rhythm ?? '—' }}
              </div>
              <div class="text-xs text-muted-foreground">节奏对齐</div>
            </div>
          </div>

          <div class="text-sm font-medium">分拍明细</div>
          <div class="max-h-64 space-y-2 overflow-y-auto pr-1">
            <div v-for="p in report.phase_details" :key="p.phase" class="rounded-lg border p-3">
              <div class="mb-1.5 flex items-center justify-between text-sm">
                <span class="font-medium">
                  第 {{ p.phase }} 拍 · {{ p.cue }}
                  <Badge v-if="!p.practiced" variant="secondary" class="ml-2">未练到</Badge>
                </span>
                <span class="text-muted-foreground">参考 {{ fmtDuration(p.reference_ms) }}</span>
              </div>
              <div v-if="p.practiced" class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div class="flex items-center gap-2">
                  <span class="w-14 text-muted-foreground">匹配</span>
                  <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      class="h-full rounded-full"
                      :style="{ width: (p.match ?? 0) + '%', background: scoreColor(p.match ?? 0) }"
                    ></div>
                  </div>
                  <span class="w-8 text-right font-medium" :style="{ color: scoreColor(p.match ?? 0) }">
                    {{ p.match }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-14 text-muted-foreground">规范</span>
                  <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      class="h-full rounded-full"
                      :style="{ width: (p.form ?? 0) + '%', background: scoreColor(p.form ?? 0) }"
                    ></div>
                  </div>
                  <span class="w-8 text-right font-medium" :style="{ color: scoreColor(p.form ?? 0) }">
                    {{ p.form }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- AI 训练建议 -->
          <div class="rounded-lg border border-primary/30 bg-primary/5 p-3">
            <div class="mb-1.5 flex items-center justify-between">
              <div class="flex items-center gap-1.5 text-sm font-medium">
                <Sparkles class="size-4 text-primary" />
                AI 训练建议
              </div>
              <button
                v-if="!detail?.advice"
                class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                :disabled="adviceLoading"
                @click="refreshAdvice"
              >
                <Loader2 v-if="adviceLoading" class="size-3 animate-spin" />
                刷新
              </button>
            </div>
            <p v-if="detail?.advice" class="whitespace-pre-wrap text-sm leading-relaxed">
              {{ detail.advice }}
            </p>
            <p v-else class="text-xs text-muted-foreground">
              建议由 DeepSeek 在训练结束后生成，若刚结束训练请稍候点击刷新
            </p>
          </div>
        </template>
        <div v-else class="py-6 text-center text-sm text-muted-foreground">
          该记录没有详细报告（旧版本数据或自由训练）
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
