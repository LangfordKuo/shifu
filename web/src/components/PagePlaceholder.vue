<script setup lang="ts">
import { Construction } from 'lucide-vue-next';
import {
  Card,
  CardContent,
} from '@/components/ui/card';

defineProps<{
  title: string;
  description: string;
  milestone?: string;
}>();
</script>

<template>
  <div>
    <h1 class="mb-1 text-2xl font-bold">{{ title }}</h1>
    <p class="mb-6 text-sm text-muted-foreground">{{ description }}</p>
    <Card class="border-dashed">
      <CardContent
        class="flex flex-col items-center justify-center gap-3 py-16 text-center"
      >
        <Construction class="size-10 text-muted-foreground/60" />
        <p class="font-medium">功能建设中</p>
        <p class="max-w-md text-sm text-muted-foreground">
          {{ milestone ?? '该模块将在后续迭代中上线' }}
        </p>
      </CardContent>
    </Card>
  </div>
</template>
