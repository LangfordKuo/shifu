/** 浏览器 TTS：零延迟本地合成，带同句/全局冷却，避免刷屏。 */

let lastText = '';
let lastAt = 0;

export function ttsSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/**
 * 播报一条建议。
 * 规则：同一句话 8 秒内不重复；正在播报时 3 秒内不插话（播最新、打断旧的）。
 */
export function speak(text: string, enabled: boolean) {
  if (!enabled || !ttsSupported() || !text) return;
  const now = Date.now();
  if (text === lastText && now - lastAt < 8000) return;
  if (window.speechSynthesis.speaking && now - lastAt < 3000) return;

  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = 'zh-CN';
  utter.rate = 1.1;
  utter.pitch = 1;
  lastText = text;
  lastAt = now;
  window.speechSynthesis.speak(utter);
}

export function stopSpeaking() {
  if (ttsSupported()) window.speechSynthesis.cancel();
}
