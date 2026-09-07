/**
 * 带进度的文件上传（XHR），返回服务端 JSON。
 */
import { loadTokens } from '@/lib/api';

export function uploadWithProgress<T = unknown>(
  url: string,
  formData: FormData,
  onProgress: (percent: number) => void,
  timeoutMs = 10 * 60 * 1000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    const tokens = loadTokens();
    if (tokens?.accessToken) {
      xhr.setRequestHeader('Authorization', `Bearer ${tokens.accessToken}`);
    }
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* 非 JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T);
      } else {
        const message = (data as { message?: string })?.message ?? `上传失败（${xhr.status}）`;
        reject(new Error(String(message)));
      }
    };
    xhr.onerror = () => reject(new Error('网络错误，上传失败'));
    xhr.timeout = timeoutMs;
    xhr.send(formData);
  });
}
