<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { KeyRound, Loader2, PlugZap } from 'lucide-vue-next';
import { toast } from 'vue-sonner';
import { api } from '@/lib/api';
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
import { Switch } from '@/components/ui/switch';

interface AiConfigView {
  baseUrl: string;
  model: string;
  enabled: boolean;
  keyConfigured: boolean;
}

const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const keyConfigured = ref(false);
const testResult = ref<{ ok: boolean; message: string } | null>(null);

const form = reactive({
  baseUrl: '',
  model: '',
  apiKey: '', // 留空 = 保留已配置密钥
  enabled: true,
});

onMounted(async () => {
  try {
    const cfg = await api.get<AiConfigView>('/admin/ai-config');
    form.baseUrl = cfg.baseUrl;
    form.model = cfg.model;
    form.enabled = cfg.enabled;
    keyConfigured.value = cfg.keyConfigured;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载配置失败');
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  try {
    const view = await api.put<AiConfigView>('/admin/ai-config', {
      baseUrl: form.baseUrl,
      model: form.model,
      ...(form.apiKey ? { apiKey: form.apiKey.trim() } : {}),
      enabled: form.enabled,
    });
    keyConfigured.value = view.keyConfigured;
    toast.success(view.enabled ? '已保存，AI 建议已启用' : '已保存，AI 建议已停用');
    form.apiKey = '';
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存失败');
  } finally {
    saving.value = false;
  }
}

async function testConnection() {
  testing.value = true;
  testResult.value = null;
  try {
    // 若输入了新密钥，先暂存再测试
    if (form.apiKey.trim()) {
      await api.put('/admin/ai-config', { apiKey: form.apiKey.trim() });
      form.apiKey = '';
    }
    const res = await api.post<{ ok: boolean; message: string }>(
      '/admin/ai-config/test',
    );
    testResult.value = res;
  } catch (err) {
    testResult.value = {
      ok: false,
      message: err instanceof Error ? err.message : '测试失败',
    };
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold">AI 接口设置</h1>
      <p class="text-sm text-muted-foreground">
        配置 DeepSeek 接口，训练结束后自动生成个性化训练建议
      </p>
    </div>

    <Card class="max-w-xl">
      <CardHeader>
        <CardTitle class="flex items-center gap-2 text-base">
          <KeyRound class="size-4" />
          DeepSeek 接口
        </CardTitle>
        <CardDescription>
          密钥仅保存在服务器数据库，不会下发到浏览器
        </CardDescription>
      </CardHeader>
      <CardContent v-if="!loading" class="space-y-4">
        <div class="space-y-2">
          <Label for="ai-base">接口地址</Label>
          <Input id="ai-base" v-model="form.baseUrl" placeholder="https://api.deepseek.com" />
        </div>
        <div class="space-y-2">
          <Label for="ai-model">模型</Label>
          <Input id="ai-model" v-model="form.model" placeholder="deepseek-v4-flash" />
          <p class="text-xs text-muted-foreground">
            当前 DeepSeek 官方模型标识：deepseek-v4-flash / deepseek-v4-pro
          </p>
        </div>
        <div class="space-y-2">
          <Label for="ai-key">API Key</Label>
          <Input
            id="ai-key"
            v-model="form.apiKey"
            type="password"
            :placeholder="keyConfigured ? '已配置（输入新值可更换）' : '请输入 DeepSeek API Key'"
          />
        </div>
        <div class="flex items-center justify-between rounded-lg border p-3">
          <div>
            <div class="text-sm font-medium">启用 AI 训练建议</div>
            <div class="text-xs text-muted-foreground">每次课程训练结束后自动调用</div>
          </div>
          <Switch v-model="form.enabled" />
        </div>

        <div
          v-if="testResult"
          class="rounded-lg p-3 text-sm"
          :class="testResult.ok ? 'bg-green-500/10 text-green-600' : 'bg-destructive/10 text-destructive'"
        >
          {{ testResult.ok ? '✓ ' : '✕ ' }}{{ testResult.message }}
        </div>

        <div class="flex gap-2 pt-1">
          <Button :disabled="saving" @click="save">
            <Loader2 v-if="saving" class="animate-spin" />
            保存设置
          </Button>
          <Button variant="outline" :disabled="testing" @click="testConnection">
            <Loader2 v-if="testing" class="animate-spin" />
            <PlugZap v-else />
            测试连接
          </Button>
        </div>
      </CardContent>
      <CardContent v-else class="py-10 text-center text-sm text-muted-foreground">
        加载中…
      </CardContent>
    </Card>
  </div>
</template>
