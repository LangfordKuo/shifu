<script setup lang="ts">
import { computed } from 'vue';
import { BookOpen, History, Sparkles, Video } from 'lucide-vue-next';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return '夜深了';
  if (h < 12) return '早上好';
  if (h < 18) return '下午好';
  return '晚上好';
});

const entries = [
  {
    title: '选择课程',
    description: '浏览已上线的训练课程',
    icon: BookOpen,
    to: '/courses',
  },
  {
    title: '开始训练',
    description: '打开摄像头，AI 实时纠正动作',
    icon: Video,
    to: '/train',
  },
  {
    title: '训练记录',
    description: '回顾历史成绩与改进建议',
    icon: History,
    to: '/history',
  },
];
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">
          {{ greeting }}，{{ auth.user?.nickname ?? auth.user?.username }}
        </h1>
        <p class="text-sm text-muted-foreground">
          今天也要坚持练习，功到自然成
        </p>
      </div>
      <Badge variant="secondary" class="gap-1">
        <Sparkles class="size-3" />
        {{ auth.isAdmin ? '管理员' : '学员' }}
      </Badge>
    </div>

    <div class="grid gap-4 sm:grid-cols-3">
      <Card
        v-for="entry in entries"
        :key="entry.to"
        class="transition-colors hover:border-ring"
      >
        <CardHeader>
          <entry.icon class="mb-2 size-8 text-primary" />
          <CardTitle class="text-base">{{ entry.title }}</CardTitle>
          <CardDescription>{{ entry.description }}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" size="sm" as-child>
            <RouterLink :to="entry.to">前往</RouterLink>
          </Button>
        </CardContent>
      </Card>
    </div>

    <Card class="mt-6">
      <CardHeader>
        <CardTitle class="text-base">下一步：实时动作训练</CardTitle>
        <CardDescription>
          M2 里程碑将上线摄像头实时推理：YOLO 姿态识别 + 关节角度评分 + TTS 语音纠偏
        </CardDescription>
      </CardHeader>
    </Card>
  </div>
</template>
