import { defineStore } from 'pinia';
import { api, loadTokens, saveTokens, type Tokens } from '@/lib/api';

export interface CurrentUser {
  id: number;
  username: string;
  nickname: string | null;
  role: 'ADMIN' | 'USER';
  status: string;
}

interface LoginResult extends Tokens {
  user: CurrentUser;
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as CurrentUser | null,
    loaded: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.user,
    isAdmin: (s) => s.user?.role === 'ADMIN',
  },
  actions: {
    async login(username: string, password: string) {
      const result = await api.post<LoginResult>('/auth/login', {
        username,
        password,
      });
      saveTokens({
        accessToken: result.accessToken,
        refreshToken: result.refreshToken,
      });
      this.user = result.user;
      this.loaded = true;
    },

    /** 启动时调用：有 token 则拉取当前用户，无效则清空 */
    async fetchMe() {
      if (!loadTokens()?.accessToken) {
        this.user = null;
        this.loaded = true;
        return;
      }
      try {
        this.user = await api.get<CurrentUser>('/auth/me');
      } catch {
        saveTokens(null);
        this.user = null;
      } finally {
        this.loaded = true;
      }
    },

    async logout() {
      const tokens = loadTokens();
      try {
        if (tokens?.refreshToken) {
          await api.post('/auth/logout', { refreshToken: tokens.refreshToken });
        }
      } catch {
        // 忽略登出接口失败
      }
      saveTokens(null);
      this.user = null;
    },
  },
});
