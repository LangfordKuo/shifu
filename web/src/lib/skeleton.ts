/**
 * 骨架绘制（COCO 17 关键点）：骨架连线 + 关键点 + 太极教学辅助线 + 关节角度弧。
 * 画布尺寸与原始视频帧一致，坐标为归一化关键点 × 画布宽高。
 * 镜像由外层容器 CSS 统一处理，这里始终按原始帧坐标绘制。
 */
import type { Landmark } from '@/lib/trainClient';

const GOLD = '#d4af37';
const JADE = '#00d4a0';
const RED = '#e74c3c';
const GRAY = '#9aa4ae';

const CONNECTIONS: [number, number][] = [
  [5, 6], // 肩线
  [5, 7], [7, 9], // 左臂
  [6, 8], [8, 10], // 右臂
  [5, 11], [6, 12], [11, 12], // 躯干
  [11, 13], [13, 15], // 左腿
  [12, 14], [14, 16], // 右腿
  [0, 5], [0, 6], // 头-肩
];

// 角度弧：肘（红）与膝（金）
const ARCS: [number, number, number, string][] = [
  [5, 7, 9, RED], // 左肘
  [6, 8, 10, RED], // 右肘
  [11, 13, 15, GOLD], // 左膝
  [12, 14, 16, GOLD], // 右膝
];

interface Pt {
  x: number;
  y: number;
}

export function drawSkeleton(
  canvas: HTMLCanvasElement,
  landmarks: Landmark[],
  opts: {
    drawGuides?: boolean;
    background?: HTMLImageElement | null;
    /** 标准姿态（课程关键帧归一化 pose），适配到用户身体后以金色叠加对比 */
    ghost?: Array<{ x: number; y: number; v: number }> | null;
  } = {},
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 背景图（演示模式）：清屏后立即绘制，保证位于骨架下方
  if (opts.background) {
    try {
      ctx.drawImage(opts.background, 0, 0, canvas.width, canvas.height);
    } catch {
      // 图片未就绪时忽略
    }
  }

  const w = canvas.width;
  const h = canvas.height;
  const ok = (i: number) => landmarks[i] && landmarks[i].v > 0.3;
  const px = (i: number): Pt => ({ x: landmarks[i].x * w, y: landmarks[i].y * h });
  const drawGuides = opts.drawGuides !== false;

  // ---------- 标准姿态叠加（ghost）：适配到用户当前身体位置 ----------
  if (opts.ghost && ok(5) && ok(6) && ok(11) && ok(12)) {
    const kp = [px(5), px(6), px(11), px(12)];
    const hipMid = { x: (kp[2].x + kp[3].x) / 2, y: (kp[2].y + kp[3].y) / 2 };
    const shMid = { x: (kp[0].x + kp[1].x) / 2, y: (kp[0].y + kp[1].y) / 2 };
    const torso = Math.hypot(shMid.x - hipMid.x, shMid.y - hipMid.y);
    if (torso > 8) {
      const g = opts.ghost;
      const gok = (i: number) => g[i] && g[i].v > 0.3;
      const gpx = (i: number): Pt => ({
        x: hipMid.x + g[i].x * torso,
        y: hipMid.y + g[i].y * torso,
      });
      ctx.save();
      ctx.globalAlpha = 0.55;
      ctx.lineCap = 'round';
      // ghost 连线（金色）
      for (const [s, e] of CONNECTIONS) {
        if (gok(s) && gok(e)) {
          const sp = gpx(s);
          const ep = gpx(e);
          ctx.strokeStyle = GOLD;
          ctx.lineWidth = 3;
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(sp.x, sp.y);
          ctx.lineTo(ep.x, ep.y);
          ctx.stroke();
        }
      }
      // ghost 关键点（空心金圈）
      for (const p of g) {
        if (p.v > 0.3) {
          ctx.strokeStyle = GOLD;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(p.x * torso + hipMid.x, p.y * torso + hipMid.y, 4, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
  }

  // ---------- 太极教学辅助线 ----------
  if (drawGuides) {
    // 1) 中轴中正线：头顶 → 双踝中点（金色虚线）
    if (ok(0) && ok(15) && ok(16)) {
      const top = px(0);
      const ankleA = px(15);
      const ankleB = px(16);
      const footMid = { x: (ankleA.x + ankleB.x) / 2, y: (ankleA.y + ankleB.y) / 2 };
      dashedLine(ctx, top, footMid, GOLD, 2, [14, 6]);
    }
    // 2) 躯干轴线：肩中点 → 髋中点（翠绿实线）
    if (ok(5) && ok(6) && ok(11) && ok(12)) {
      const s = px(5);
      const s2 = px(6);
      const hp = px(11);
      const hp2 = px(12);
      solidLine(
        ctx,
        { x: (s.x + s2.x) / 2, y: (s.y + s2.y) / 2 },
        { x: (hp.x + hp2.x) / 2, y: (hp.y + hp2.y) / 2 },
        JADE,
        1.5,
      );
    }
    // 3) 重心投影线：髋中点垂直向下（灰色）
    if (ok(11) && ok(12) && ok(15) && ok(16)) {
      const hp = px(11);
      const hp2 = px(12);
      const hipMid = { x: (hp.x + hp2.x) / 2, y: (hp.y + hp2.y) / 2 };
      const footY = Math.max(px(15).y, px(16).y) + 30;
      solidLine(ctx, hipMid, { x: hipMid.x, y: Math.min(footY, h - 1) }, GRAY, 1);
    }
    // 4) 地面水平线（灰色虚线）
    if (ok(15) && ok(16)) {
      const a = px(15);
      const b = px(16);
      const footY = Math.max(a.y, b.y) + 18;
      const leftX = Math.max(Math.min(a.x, b.x) - 60, 0);
      const rightX = Math.min(Math.max(a.x, b.x) + 60, w - 1);
      dashedLine(ctx, { x: leftX, y: footY }, { x: rightX, y: footY }, GRAY, 1, [10, 5]);
    }
    // 5) 关节角度弧
    for (const [a, b, c, color] of ARCS) {
      if (ok(a) && ok(b) && ok(c)) angleArc(ctx, px(a), px(b), px(c), color);
    }
  }

  // ---------- 骨架 ----------
  ctx.lineCap = 'round';
  for (const [s, e] of CONNECTIONS) {
    if (ok(s) && ok(e)) {
      const sp = px(s);
      const ep = px(e);
      ctx.strokeStyle = JADE;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(sp.x, sp.y);
      ctx.lineTo(ep.x, ep.y);
      ctx.stroke();
    }
  }

  // ---------- 关键点 ----------
  for (const p of landmarks) {
    if (p.v > 0.3) {
      ctx.fillStyle = RED;
      ctx.beginPath();
      ctx.arc(p.x * w, p.y * h, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }
}

function solidLine(ctx: CanvasRenderingContext2D, a: Pt, b: Pt, color: string, width: number) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
}

function dashedLine(
  ctx: CanvasRenderingContext2D,
  a: Pt,
  b: Pt,
  color: string,
  width: number,
  dash: number[],
) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
  ctx.setLineDash([]);
}

function angleArc(ctx: CanvasRenderingContext2D, a: Pt, b: Pt, c: Pt, color: string) {
  const rA = Math.hypot(a.x - b.x, a.y - b.y);
  const rC = Math.hypot(c.x - b.x, c.y - b.y);
  const r = Math.max(14, Math.min((rA + rC) / 4, 40));
  const angA = Math.atan2(a.y - b.y, a.x - b.x);
  const angC = Math.atan2(c.y - b.y, c.x - b.x);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(b.x, b.y, r, Math.min(angA, angC), Math.max(angA, angC));
  ctx.stroke();
}
