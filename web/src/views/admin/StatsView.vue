<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { toast } from 'vue-sonner';
import { api } from '@/lib/api';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface Stats {
  users: number;
  courses: number;
  published: number;
  sessions: number;
  avgScore: number | null;
  recent: Array<{
    id: number;
    user: string;
    course: string;
    score: number | null;
    durationMs: number;
    createdAt: string;
  }>;
  courseScores: Array<{
    courseId: number;
    title: string;
    sessions: number;
    avgScore: number | null;
  }>;
}

const stats = ref<Stats | null>(null);
const loading = ref(true);

onMounted(async () => {
  try {
    stats.value = await api.get<Stats>('/admin/stats');
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载统计失败');
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

const maxSessions = () =>
  Math.max(1, ...(stats.value?.courseScores.map((c) => c.sessions) ?? [1]));
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold">数据统计</h1>
      <p class="text-sm text-muted-foreground">平台运营与训练情况一览</p>
    </div>

    <div v-if="loading" class="py-16 text-center text-muted-foreground">加载中…</div>

    <template v-else-if="stats">
      <!-- 概览卡片 -->
      <div class="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <Card v-for="item in [
          { label: '用户数', value: stats.users },
          { label: '课程总数', value: stats.courses },
          { label: '已发布', value: stats.published },
          { label: '训练次数', value: stats.sessions },
          { label: '平均得分', value: stats.avgScore ?? '—' },
        ]" :key="item.label">
          <CardContent class="pt-6">
            <div class="text-3xl font-bold">{{ item.value }}</div>
            <div class="mt-1 text-xs text-muted-foreground">{{ item.label }}</div>
          </CardContent>
        </Card>
      </div>

      <div class="mt-6 grid gap-4 lg:grid-cols-2">
        <!-- 课程训练量 -->
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-base">课程训练量与平均分</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3">
            <p v-if="stats.courseScores.length === 0" class="text-sm text-muted-foreground">
              暂无训练数据
            </p>
            <div v-for="c in stats.courseScores" :key="c.courseId">
              <div class="mb-1 flex items-center justify-between text-sm">
                <span class="max-w-56 truncate font-medium">{{ c.title }}</span>
                <span class="text-xs text-muted-foreground">
                  {{ c.sessions }} 次
                  <span v-if="c.avgScore != null" :style="{ color: scoreColor(c.avgScore) }" class="ml-2 font-semibold">
                    均 {{ c.avgScore }}
                  </span>
                </span>
              </div>
              <div class="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  class="h-full rounded-full bg-primary transition-all"
                  :style="{ width: (c.sessions / maxSessions()) * 100 + '%' }"
                ></div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- 最近训练 -->
        <Card>
          <CardHeader class="pb-2">
            <CardTitle class="text-base">最近训练</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>学员</TableHead>
                  <TableHead>课程</TableHead>
                  <TableHead>得分</TableHead>
                  <TableHead>时长</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-if="stats.recent.length === 0">
                  <TableCell colspan="5" class="h-16 text-center text-muted-foreground">
                    暂无训练记录
                  </TableCell>
                </TableRow>
                <TableRow v-for="s in stats.recent" :key="s.id">
                  <TableCell class="font-medium">{{ s.user }}</TableCell>
                  <TableCell class="max-w-32 truncate">{{ s.course }}</TableCell>
                  <TableCell>
                    <span v-if="s.score != null" class="font-semibold" :style="{ color: scoreColor(s.score) }">
                      {{ s.score.toFixed(1) }}
                    </span>
                    <span v-else>—</span>
                  </TableCell>
                  <TableCell class="text-muted-foreground">{{ fmtDuration(s.durationMs) }}</TableCell>
                  <TableCell class="text-muted-foreground">{{ fmtTime(s.createdAt) }}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>
