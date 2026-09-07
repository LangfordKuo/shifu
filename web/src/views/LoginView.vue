<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Swords } from 'lucide-vue-next';
import { toast } from 'vue-sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const username = ref('');
const password = ref('');
const loading = ref(false);

async function onSubmit() {
  if (!username.value || !password.value) return;
  loading.value = true;
  try {
    await auth.login(username.value.trim(), password.value);
    toast.success('登录成功');
    router.push((route.query.redirect as string) ?? '/');
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '登录失败');
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-background p-4">
    <Card class="w-full max-w-sm">
      <CardHeader class="text-center">
        <div class="mx-auto mb-2 flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Swords class="size-6" />
        </div>
        <CardTitle class="text-xl">shifu · AI 武术动作指导</CardTitle>
        <CardDescription>登录后开始你的训练</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-4" @submit.prevent="onSubmit">
          <div class="space-y-2">
            <Label for="username">用户名</Label>
            <Input
              id="username"
              v-model="username"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </div>
          <div class="space-y-2">
            <Label for="password">密码</Label>
            <Input
              id="password"
              v-model="password"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
            />
          </div>
          <Button type="submit" class="w-full" :disabled="loading">
            {{ loading ? '登录中…' : '登 录' }}
          </Button>
          <p class="text-center text-xs text-muted-foreground">
            没有账号？请联系管理员开通
          </p>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
