<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { Clock, ListOrdered, Play } from 'lucide-vue-next';
import { toast } from 'vue-sonner';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
} from '@/components/ui/card';

interface CourseItem {
  id: number;
  title: string;
  description: string | null;
  category: string;
  coverUrl: string | null;
  keyframeCount: number;
  durationMs: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  general: '综合',
  taiji: '太极',
  changquan: '长拳',
  taolu: '套路',
};

const courses = ref<CourseItem[]>([]);
const loading = ref(true);

onMounted(async () => {
  try {
    const data = await api.get<{ items: CourseItem[] }>('/courses');
    courses.value = data.items;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载课程失败');
  } finally {
    loading.value = false;
  }
});

function fmtDuration(ms: number) {
  const s = Math.round(ms / 1000);
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`;
}
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold">课程</h1>
      <p class="text-sm text-muted-foreground">
        选择一门课程，AI 师傅将带你逐拍练习并实时纠偏
      </p>
    </div>

    <div v-if="loading" class="py-16 text-center text-muted-foreground">加载中…</div>

    <div v-else-if="courses.length === 0" class="py-16 text-center text-muted-foreground">
      课程上架后即可开始训练
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card v-for="course in courses" :key="course.id" class="overflow-hidden p-0">
        <div class="relative aspect-video bg-muted">
          <img
            v-if="course.coverUrl"
            :src="course.coverUrl"
            :alt="course.title"
            class="h-full w-full object-cover"
          />
          <div v-else class="flex h-full items-center justify-center">
            <Play class="size-10 text-muted-foreground/50" />
          </div>
          <Badge class="absolute left-3 top-3" variant="secondary">
            {{ CATEGORY_LABELS[course.category] ?? course.category }}
          </Badge>
        </div>
        <CardContent class="space-y-3 p-4">
          <div>
            <div class="font-semibold">{{ course.title }}</div>
            <p v-if="course.description" class="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
              {{ course.description }}
            </p>
          </div>
          <div class="flex items-center gap-4 text-xs text-muted-foreground">
            <span class="flex items-center gap-1">
              <ListOrdered class="size-3.5" />
              {{ course.keyframeCount }} 拍
            </span>
            <span v-if="course.durationMs" class="flex items-center gap-1">
              <Clock class="size-3.5" />
              {{ fmtDuration(course.durationMs) }}
            </span>
          </div>
          <Button class="w-full" as-child>
            <RouterLink :to="`/train?course=${course.id}`">开始训练</RouterLink>
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
