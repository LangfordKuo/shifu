/**
 * 实时训练 WebSocket 客户端。
 * 协议见 ai/app/api/train_ws.py；走 Vite/nginx 的 /ai 代理。
 */
import { loadTokens } from '@/lib/api';

export interface Landmark {
  x: number;
  y: number;
  v: number;
}

export interface ScoreItem {
  name: string;
  score: number;
  angle: number | null;
}

export interface Deviation {
  joint: string;
  name: string;
  target: number;
  actual: number;
  delta: number;
  text: string;
  /** 面向语音播报的口语短句（不带数字） */
  spoken?: string;
}

export interface TrainResult {
  type: 'result';
  landmarks?: Landmark[];
  angles?: Record<string, number>;
  score?: number;
  items?: ScoreItem[];
  suggestions?: string[];
  inference_ms?: number;
  error?: string;
  // ---- 课程模式字段 ----
  phase?: number;
  phase_total?: number;
  cue?: string;
  phase_changed?: boolean;
  finished?: boolean;
  session_done?: boolean;
  match_score?: number;
  progress?: number;
  deviations?: Deviation[];
  /** 当前拍的标准姿态（归一化），用于贴身叠加对比 */
  ghost?: Array<{ x: number; y: number; v: number }>;
  /** 姿态达标且无偏差 */
  all_good?: boolean;
  /** 当前拍首次达标（true 仅在达标那一帧） */
  hold_done?: boolean;
  /** 达标后等待进入下一拍的剩余毫秒（未达标时为 null） */
  hold_remaining_ms?: number | null;
}

export type WsMessage =
  | { type: 'auth_ok'; username: string }
  | { type: 'reset_ok' }
  | { type: 'pong'; ts: number }
  | { type: 'error'; message: string }
  | TrainResult;

export type ConnStatus = 'idle' | 'connecting' | 'ready' | 'closed' | 'error';

export function trainWsUrl() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${location.host}/ai/ws/train`;
}

export class TrainClient {
  private ws: WebSocket | null = null;
  private pending: ((r: TrainResult | null) => void) | null = null;

  status: ConnStatus = 'idle';
  username = '';

  onStatus: (s: ConnStatus, message?: string) => void = () => {};
  onResult: (r: TrainResult) => void = () => {};

  /** 连接并完成 JWT 鉴权；成功返回 true */
  connect(): Promise<boolean> {
    const token = loadTokens()?.accessToken;
    if (!token) {
      this.setStatus('error', '未登录');
      return Promise.resolve(false);
    }
    this.setStatus('connecting');
    return new Promise((resolve) => {
      const ws = new WebSocket(trainWsUrl());
      ws.binaryType = 'arraybuffer';
      this.ws = ws;

      const timeout = setTimeout(() => {
        if (this.status !== 'ready') {
          this.setStatus('error', '连接超时');
          ws.close();
          resolve(false);
        }
      }, 8000);

      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }));
      ws.onmessage = (ev) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(ev.data as string) as WsMessage;
        } catch {
          return;
        }
        if (msg.type === 'auth_ok') {
          clearTimeout(timeout);
          this.username = msg.username;
          this.setStatus('ready');
          resolve(true);
          return;
        }
        if (msg.type === 'result') {
          const pending = this.pending;
          this.pending = null;
          pending?.(msg);
          this.onResult(msg);
          return;
        }
        if (msg.type === 'error') {
          if (this.status !== 'ready') {
            clearTimeout(timeout);
            this.setStatus('error', msg.message);
            resolve(false);
          }
        }
      };
      ws.onclose = () => {
        clearTimeout(timeout);
        this.ws = null;
        const pending = this.pending;
        this.pending = null;
        pending?.(null);
        if (this.status !== 'error') this.setStatus('closed');
      };
      ws.onerror = () => {
        if (this.status !== 'ready') {
          clearTimeout(timeout);
          this.setStatus('error', '无法连接 AI 服务');
          resolve(false);
        }
      };
    });
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** 发送一帧 JPEG；返回结果（连接断开/超时返回 null） */
  sendFrame(jpeg: ArrayBuffer, timeoutMs = 5000): Promise<TrainResult | null> {
    if (!this.isConnected) return Promise.resolve(null);
    return new Promise((resolve) => {
      this.pending = resolve;
      this.ws!.send(jpeg);
      setTimeout(() => {
        if (this.pending === resolve) {
          this.pending = null;
          resolve(null);
        }
      }, timeoutMs);
    });
  }

  sendReset() {
    if (this.isConnected) this.ws!.send(JSON.stringify({ type: 'reset' }));
  }

  /** 发送控制消息（set_wait / skip_phase 等，无需等待响应） */
  sendControl(msg: object) {
    if (this.isConnected) this.ws!.send(JSON.stringify(msg));
  }

  /** 发送控制消息并等待指定类型响应（超时/错误返回 null） */
  sendAndWait<T = { type: string }>(
    msg: object,
    expectType: string,
    timeoutMs = 10000,
  ): Promise<T | null> {
    if (!this.isConnected) return Promise.resolve(null);
    return new Promise((resolve) => {
      const ws = this.ws!;
      const handler = (ev: MessageEvent) => {
        let data: { type: string } | null = null;
        try {
          data = JSON.parse(ev.data as string);
        } catch {
          return;
        }
        if (data && (data.type === expectType || data.type === 'error')) {
          ws.removeEventListener('message', handler);
          clearTimeout(timer);
          resolve(data.type === 'error' ? null : (data as T));
        }
      };
      const timer = setTimeout(() => {
        ws.removeEventListener('message', handler);
        resolve(null);
      }, timeoutMs);
      ws.addEventListener('message', handler);
      ws.send(JSON.stringify(msg));
    });
  }

  close() {
    this.ws?.close();
    this.ws = null;
  }

  private setStatus(s: ConnStatus, message?: string) {
    this.status = s;
    this.onStatus(s, message);
  }
}
