import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

const KEY_BASE_URL = 'ai.baseUrl';
const KEY_MODEL = 'ai.model';
const KEY_API_KEY = 'ai.apiKey';
const KEY_ENABLED = 'ai.enabled';

const DEFAULT_BASE_URL = 'https://api.deepseek.com';
const DEFAULT_MODEL = 'deepseek-v4-flash';

export interface AiSettings {
  baseUrl: string;
  model: string;
  apiKey: string;
  enabled: boolean;
}

@Injectable()
export class AiConfigService {
  private readonly logger = new Logger(AiConfigService.name);

  constructor(private prisma: PrismaService) {}

  async getSettings(): Promise<AiSettings> {
    const rows = await this.prisma.systemConfig.findMany({
      where: { key: { in: [KEY_BASE_URL, KEY_MODEL, KEY_API_KEY, KEY_ENABLED] } },
    });
    const map = new Map(rows.map((r) => [r.key, r.value]));
    return {
      baseUrl: map.get(KEY_BASE_URL) ?? DEFAULT_BASE_URL,
      model: map.get(KEY_MODEL) ?? DEFAULT_MODEL,
      apiKey: map.get(KEY_API_KEY) ?? '',
      enabled: (map.get(KEY_ENABLED) ?? 'true') === 'true',
    };
  }

  async updateSettings(dto: {
    baseUrl?: string;
    model?: string;
    /** undefined=保留原值；''=清除；非空=设置新值 */
    apiKey?: string;
    enabled?: boolean;
  }) {
    const upserts: Array<{ key: string; value: string }> = [];
    if (dto.baseUrl !== undefined) upserts.push({ key: KEY_BASE_URL, value: dto.baseUrl.trim() });
    if (dto.model !== undefined) upserts.push({ key: KEY_MODEL, value: dto.model.trim() });
    if (dto.enabled !== undefined) upserts.push({ key: KEY_ENABLED, value: String(dto.enabled) });
    if (dto.apiKey !== undefined) upserts.push({ key: KEY_API_KEY, value: dto.apiKey.trim() });

    for (const { key, value } of upserts) {
      await this.prisma.systemConfig.upsert({
        where: { key },
        update: { value },
        create: { key, value },
      });
    }
    return this.publicView();
  }

  /** 管理端展示：不回传明文密钥 */
  async publicView() {
    const s = await this.getSettings();
    return {
      baseUrl: s.baseUrl,
      model: s.model,
      enabled: s.enabled,
      keyConfigured: s.apiKey.length > 0,
    };
  }

  /** 调用 chat/completions，返回文本；失败抛错 */
  async chat(messages: Array<{ role: string; content: string }>, maxTokens = 400) {
    const s = await this.getSettings();
    if (!s.apiKey) throw new Error('尚未配置 AI 服务密钥');
    const base = s.baseUrl.replace(/\/+$/, '');
    const resp = await fetch(`${base}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${s.apiKey}`,
      },
      body: JSON.stringify({
        model: s.model,
        messages,
        temperature: 0.7,
        max_tokens: maxTokens,
        stream: false,
      }),
      signal: AbortSignal.timeout(60_000),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`AI 接口响应 ${resp.status}：${text.slice(0, 200)}`);
    }
    const data = (await resp.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    const content = data.choices?.[0]?.message?.content?.trim();
    if (!content) throw new Error('AI 接口返回内容为空');
    return content;
  }

  async testConnection() {
    try {
      const reply = await this.chat(
        [{ role: 'user', content: '请回复"连接成功"四个字' }],
        20,
      );
      return { ok: true, message: reply };
    } catch (err) {
      return { ok: false, message: err instanceof Error ? err.message : String(err) };
    }
  }

  /** 训练结束后生成个性化建议（后台异步，失败静默留空） */
  async generateAdviceForSession(sessionId: number) {
    try {
      const s = await this.getSettings();
      if (!s.enabled || !s.apiKey) return;

      const session = await this.prisma.trainingSession.findUnique({
        where: { id: sessionId },
        include: { course: { select: { title: true } } },
      });
      if (!session) return;

      const report = session.reportJson ? JSON.parse(session.reportJson) : null;
      const summary = {
        课程: session.course.title,
        综合得分: session.score,
        训练时长秒: Math.round(session.durationMs / 1000),
        ...(report
          ? {
              动作规范: report.form,
              关键帧匹配: report.match,
              节奏对齐: report.rhythm,
              完成拍: `${report.phases_practiced ?? '?'}/${report.phase_total ?? '?'}`,
              分拍明细: (report.phase_details ?? []).map((p: Record<string, unknown>) => ({
                口令: p.cue,
                匹配分: p.match,
                规范分: p.form,
                是否练到: p.practiced,
              })),
            }
          : {}),
      };

      const advice = await this.chat([
        {
          role: 'system',
          content:
            '你是一位专业的武术教练AI助手。根据学员的训练数据报告，给出针对性的训练建议。' +
            '要求：最多3条，每条一句话（不超过30字），口语化中文，结合数据指出最薄弱的环节并给出具体练习方法，不要客套话。' +
            '直接以序号列表输出，不要其他内容。',
        },
        { role: 'user', content: JSON.stringify(summary, null, 1) },
      ]);

      await this.prisma.trainingSession.update({
        where: { id: sessionId },
        data: { advice },
      });
      this.logger.log(`会话 ${sessionId} 训练建议已生成`);
    } catch (err) {
      this.logger.warn(`会话 ${sessionId} 训练建议生成失败：${err instanceof Error ? err.message : err}`);
    }
  }
}
