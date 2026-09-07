<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  BookOpen,
  History,
  Home,
  LogOut,
  ShieldCheck,
  Swords,
  Users,
  Video,
} from 'lucide-vue-next';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

interface NavItem {
  label: string;
  to: string;
  icon: typeof Home;
  roles?: string[];
}

const navGroups = computed(() => [
  {
    title: '训练',
    items: [
      { label: '概览', to: '/', icon: Home },
      { label: '课程', to: '/courses', icon: BookOpen },
      { label: '开始训练', to: '/train', icon: Video },
      { label: '训练记录', to: '/history', icon: History },
    ] as NavItem[],
  },
  {
    title: '管理',
    items: [
      { label: '用户管理', to: '/admin/users', icon: Users, roles: ['ADMIN'] },
      { label: '课程管理', to: '/admin/courses', icon: ShieldCheck, roles: ['ADMIN'] },
    ] as NavItem[],
  },
]);

const visibleGroups = computed(() =>
  navGroups.value
    .map((g) => ({
      ...g,
      items: g.items.filter((i) => !i.roles || i.roles.includes(auth.user?.role ?? '')),
    }))
    .filter((g) => g.items.length > 0),
);

async function onLogout() {
  await auth.logout();
  router.push({ name: 'login' });
}
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <!-- 侧边栏 -->
    <aside class="hidden w-60 shrink-0 flex-col border-r bg-card md:flex">
      <div class="flex items-center gap-3 px-5 py-5">
        <div
          class="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"
        >
          <Swords class="size-5" />
        </div>
        <div>
          <div class="text-lg font-bold leading-tight">shifu</div>
          <div class="text-xs text-muted-foreground">AI 武术动作指导</div>
        </div>
      </div>

      <nav class="flex-1 space-y-6 overflow-y-auto px-3 py-2">
        <div v-for="group in visibleGroups" :key="group.title">
          <div class="px-2 pb-1 text-xs font-medium text-muted-foreground">
            {{ group.title }}
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            :class="
              cn(
                'mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                route.path === item.to
                  ? 'bg-accent font-medium text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
              )
            "
          >
            <component :is="item.icon" class="size-4" />
            {{ item.label }}
          </RouterLink>
        </div>
      </nav>

      <div class="border-t p-4">
        <div class="mb-3 flex items-center gap-3 px-1">
          <div
            class="flex size-8 items-center justify-center rounded-full bg-secondary text-xs font-bold"
          >
            {{ (auth.user?.nickname ?? auth.user?.username ?? '?').slice(0, 1) }}
          </div>
          <div class="min-w-0">
            <div class="truncate text-sm font-medium">
              {{ auth.user?.nickname ?? auth.user?.username }}
            </div>
            <div class="text-xs text-muted-foreground">
              {{ auth.isAdmin ? '管理员' : '学员' }}
            </div>
          </div>
        </div>
        <button
          class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
          @click="onLogout"
        >
          <LogOut class="size-4" />
          退出登录
        </button>
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="flex min-w-0 flex-1 flex-col">
      <header
        class="flex h-14 items-center gap-3 border-b bg-card/60 px-6 backdrop-blur md:hidden"
      >
        <Swords class="size-5" />
        <span class="font-bold">shifu</span>
        <button class="ml-auto text-sm text-muted-foreground" @click="onLogout">
          退出
        </button>
      </header>
      <main class="flex-1 overflow-y-auto p-6">
        <RouterView />
      </main>
    </div>
  </div>
</template>
