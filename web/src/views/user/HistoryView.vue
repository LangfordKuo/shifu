<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { toast } from 'vue-sonner';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface SessionRow {
  id: number;
  courseId: number;
  score: number | null;
  durationMs: number;
  reportJson: string | null;
  createdAt: string;
  course: { title: string };
}

const rows = ref<SessionRow[]>([]);
const loading = ref(true);

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
    const r = JSON.parse(json) as { phases?: number; phaseTotal?: number };
    return r.phases != null && r.phaseTotal ? `${r.phases}/${r.phaseTotal} 拍` : null;
  } catch {
    return null;
  }
}
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold">训练记录</h1>
      <p class="text-sm text-muted-foreground">回顾每次训练的成绩与完成度</p>
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
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-if="rows.length === 0">
              <TableCell colspan="5" class="h-24 text-center text-muted-foreground">
                {{ loading ? '加载中…' : '还没有训练记录，去上一堂课吧' }}
              </TableCell>
            </TableRow>
            <TableRow v-for="row in rows" :key="row.id">
              <TableCell class="text-muted-foreground">{{ fmtTime(row.createdAt) }}</TableCell>
              <TableCell class="font-medium">{{ row.course?.title ?? '—' }}</TableCell>
              <TableCell>
                <Badge
                  v-if="row.score != null"
                  :style="{
                    color: scoreColor(row.score),
                    borderColor: scoreColor(row.score),
                  }"
                  variant="outline"
                >
                  {{ row.score.toFixed(1) }}
                </Badge>
                <span v-else>—</span>
              </TableCell>
              <TableCell>{{ phaseInfo(row.reportJson) ?? '—' }}</TableCell>
              <TableCell class="text-muted-foreground">{{ fmtDuration(row.durationMs) }}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
</template>
