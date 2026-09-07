import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        // ---- 用户端 ----
        { path: '', name: 'dashboard', component: () => import('@/views/user/DashboardView.vue') },
        { path: 'courses', name: 'courses', component: () => import('@/views/user/CoursesView.vue') },
        { path: 'train', name: 'train', component: () => import('@/views/user/TrainView.vue') },
        { path: 'history', name: 'history', component: () => import('@/views/user/HistoryView.vue') },
        // ---- 管理端 ----
        { path: 'admin/users', name: 'admin-users', component: () => import('@/views/admin/UsersView.vue'), meta: { roles: ['ADMIN'] } },
        { path: 'admin/courses', name: 'admin-courses', component: () => import('@/views/admin/AdminCoursesView.vue'), meta: { roles: ['ADMIN'] } },
        { path: 'admin/stats', name: 'admin-stats', component: () => import('@/views/admin/StatsView.vue'), meta: { roles: ['ADMIN'] } },
        { path: 'admin/ai-settings', name: 'admin-ai-settings', component: () => import('@/views/admin/AiSettingsView.vue'), meta: { roles: ['ADMIN'] } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.loaded) await auth.fetchMe();

  if (to.meta.public) {
    return auth.isLoggedIn ? { name: 'dashboard' } : true;
  }
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } };
  }
  const roles = to.meta.roles as string[] | undefined;
  if (roles && !roles.includes(auth.user!.role)) {
    return { name: 'dashboard' };
  }
  return true;
});

export default router;
