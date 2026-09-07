<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import {
  MoreHorizontal,
  Plus,
  Search,
  ShieldCheck,
  User as UserIcon,
} from 'lucide-vue-next';
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { useAuthStore } from '@/stores/auth';

interface UserRow {
  id: number;
  username: string;
  nickname: string | null;
  role: 'ADMIN' | 'USER';
  status: 'ACTIVE' | 'DISABLED';
  createdAt: string;
}

const auth = useAuthStore();

const rows = ref<UserRow[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const keyword = ref('');
const keywordInput = ref('');
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const data = await api.get<{ items: UserRow[]; total: number }>(
      `/users?page=${page.value}&pageSize=${pageSize}&keyword=${encodeURIComponent(keyword.value)}`,
    );
    rows.value = data.items;
    total.value = data.total;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载用户列表失败');
  } finally {
    loading.value = false;
  }
}

function search() {
  keyword.value = keywordInput.value.trim();
  page.value = 1;
  load();
}

function totalPages() {
  return Math.max(1, Math.ceil(total.value / pageSize));
}

function changePage(p: number) {
  page.value = Math.min(Math.max(1, p), totalPages());
  load();
}

// ---------- 新增 / 编辑 ----------
const dialogOpen = ref(false);
const editing = ref<UserRow | null>(null);
const form = reactive({
  username: '',
  password: '',
  nickname: '',
  role: 'USER',
});

function openCreate() {
  editing.value = null;
  Object.assign(form, { username: '', password: '', nickname: '', role: 'USER' });
  dialogOpen.value = true;
}

function openEdit(row: UserRow) {
  editing.value = row;
  Object.assign(form, {
    username: row.username,
    password: '',
    nickname: row.nickname ?? '',
    role: row.role,
  });
  dialogOpen.value = true;
}

async function submitDialog() {
  try {
    if (editing.value) {
      const payload: Record<string, string> = {};
      if (form.nickname !== (editing.value.nickname ?? '')) payload.nickname = form.nickname;
      if (form.role !== editing.value.role) payload.role = form.role;
      if (form.password) payload.password = form.password;
      if (Object.keys(payload).length === 0) {
        dialogOpen.value = false;
        return;
      }
      await api.patch(`/users/${editing.value.id}`, payload);
      toast.success('用户已更新');
    } else {
      await api.post('/users', {
        username: form.username,
        password: form.password,
        nickname: form.nickname || undefined,
        role: form.role,
      });
      toast.success('用户已创建');
    }
    dialogOpen.value = false;
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '操作失败');
  }
}

// ---------- 启用 / 禁用 ----------
async function toggleStatus(row: UserRow) {
  const next = row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
  try {
    await api.patch(`/users/${row.id}`, { status: next });
    toast.success(next === 'ACTIVE' ? '已启用' : '已禁用');
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '操作失败');
  }
}

// ---------- 删除 ----------
const deleteTarget = ref<UserRow | null>(null);
const deleteOpen = ref(false);

function askDelete(row: UserRow) {
  deleteTarget.value = row;
  deleteOpen.value = true;
}

async function confirmDelete() {
  if (!deleteTarget.value) return;
  try {
    await api.delete(`/users/${deleteTarget.value.id}`);
    toast.success('用户已删除');
    deleteOpen.value = false;
    load();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除失败');
  }
}

function fmtTime(s: string) {
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">用户管理</h1>
        <p class="text-sm text-muted-foreground">
          管理平台账号、角色与启用状态
        </p>
      </div>
      <Button @click="openCreate">
        <Plus />
        新增用户
      </Button>
    </div>

    <Card>
      <CardContent class="pt-6">
        <form class="mb-4 flex max-w-sm items-center gap-2" @submit.prevent="search">
          <Input v-model="keywordInput" placeholder="搜索用户名 / 昵称" />
          <Button type="submit" variant="outline" :disabled="loading">
            <Search />
            查询
          </Button>
        </form>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead class="w-16">ID</TableHead>
              <TableHead>用户名</TableHead>
              <TableHead>昵称</TableHead>
              <TableHead>角色</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead class="w-20 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-if="rows.length === 0">
              <TableCell colspan="7" class="h-24 text-center text-muted-foreground">
                {{ loading ? '加载中…' : '暂无用户' }}
              </TableCell>
            </TableRow>
            <TableRow v-for="row in rows" :key="row.id">
              <TableCell>{{ row.id }}</TableCell>
              <TableCell class="font-medium">{{ row.username }}</TableCell>
              <TableCell>{{ row.nickname ?? '—' }}</TableCell>
              <TableCell>
                <Badge
                  :variant="row.role === 'ADMIN' ? 'default' : 'secondary'"
                  class="gap-1"
                >
                  <ShieldCheck v-if="row.role === 'ADMIN'" class="size-3" />
                  <UserIcon v-else class="size-3" />
                  {{ row.role === 'ADMIN' ? '管理员' : '学员' }}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge :variant="row.status === 'ACTIVE' ? 'outline' : 'destructive'">
                  {{ row.status === 'ACTIVE' ? '正常' : '已禁用' }}
                </Badge>
              </TableCell>
              <TableCell class="text-muted-foreground">
                {{ fmtTime(row.createdAt) }}
              </TableCell>
              <TableCell class="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger as-child>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal />
                      <span class="sr-only">操作菜单</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem @click="openEdit(row)">编辑</DropdownMenuItem>
                    <DropdownMenuItem
                      :disabled="row.id === auth.user?.id"
                      @click="toggleStatus(row)"
                    >
                      {{ row.status === 'ACTIVE' ? '禁用' : '启用' }}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      class="text-destructive"
                      :disabled="row.id === auth.user?.id"
                      @click="askDelete(row)"
                    >
                      删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>

        <div class="mt-4 flex items-center justify-end gap-3 text-sm text-muted-foreground">
          <span>共 {{ total }} 条 · 第 {{ page }}/{{ totalPages() }} 页</span>
          <Button variant="outline" size="sm" :disabled="page <= 1" @click="changePage(page - 1)">
            上一页
          </Button>
          <Button
            variant="outline"
            size="sm"
            :disabled="page >= totalPages()"
            @click="changePage(page + 1)"
          >
            下一页
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- 新增 / 编辑对话框 -->
    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{{ editing ? '编辑用户' : '新增用户' }}</DialogTitle>
          <DialogDescription>
            {{ editing ? `修改用户 ${editing.username} 的信息` : '创建一个新的平台账号' }}
          </DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit.prevent="submitDialog">
          <div class="space-y-2">
            <Label for="f-username">用户名</Label>
            <Input
              id="f-username"
              v-model="form.username"
              :disabled="!!editing"
              placeholder="2-32 位字母数字下划线"
            />
          </div>
          <div class="space-y-2">
            <Label for="f-nickname">昵称</Label>
            <Input id="f-nickname" v-model="form.nickname" placeholder="显示名称（可选）" />
          </div>
          <div class="space-y-2">
            <Label for="f-password">
              {{ editing ? '重置密码（留空表示不修改）' : '密码' }}
            </Label>
            <Input
              id="f-password"
              v-model="form.password"
              type="password"
              :placeholder="editing ? '留空则保持原密码' : '至少 6 位'"
            />
          </div>
          <div class="space-y-2">
            <Label>角色</Label>
            <Select v-model="form.role">
              <SelectTrigger class="w-full">
                <SelectValue placeholder="选择角色" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="USER">学员</SelectItem>
                <SelectItem value="ADMIN">管理员</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="dialogOpen = false">
              取消
            </Button>
            <Button type="submit">{{ editing ? '保存' : '创建' }}</Button>
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
            确定要删除用户「{{ deleteTarget?.username }}」吗？该操作不可恢复，其训练记录将一并删除。
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
