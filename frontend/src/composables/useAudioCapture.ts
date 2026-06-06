/**
 * 浏览器/WebView 音频采集 → 16kHz 单声道 s16le PCM 帧流。
 *
 * 用于「实时采集」类音源（麦克风 / 浏览器标签页 / 屏幕或窗口 / 系统音频），
 * 把采集到的音频降采样为后端 LiveTranslate 所需的 16k 单声道 PCM，按 ~100ms
 * 分帧通过 WebSocket 二进制推送。Web 工作台与桌面悬浮窗共用同一实现。
 *
 * 关键点：
 * - 用 `new AudioContext({ sampleRate: 16000 })` 让浏览器原生重采样到 16k，
 *   规避手写重采样的误差（Chrome / Edge WebView2 均支持）。
 * - 采集用 AudioWorklet（主线程外），processor 以 Blob URL 注入，无需额外构建配置，
 *   前端与桌面 Vite 工程都能直接用。
 * - 不连到 destination，避免把采集音频回放出来（自激啸叫）。
 */

const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      const channel = input[0];
      const pcm = new Int16Array(channel.length);
      for (let i = 0; i < channel.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, channel[i]));
        pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
`;

export type CaptureSourceKind = "microphone" | "browser_audio" | "screen_window" | "system_audio";

export interface AudioCaptureOptions {
  /** 收到一帧 16k 单声道 s16le PCM（ArrayBuffer，约 100ms）时回调。 */
  onChunk: (chunk: ArrayBuffer) => void;
  /** 采集异常（设备被拔出 / 轨道结束 / 权限撤销）。 */
  onError?: (message: string) => void;
  /** 用户在系统选择器里结束共享（轨道 ended）时回调。 */
  onEnded?: () => void;
  /** 目标采样率，默认 16000。 */
  sampleRate?: number;
  /** 分帧时长（ms），默认 100ms。 */
  frameMs?: number;
}

export interface AudioCaptureSession {
  stop: () => Promise<void>;
}

const TARGET_SAMPLE_RATE = 16000;

/** 按音源种类获取浏览器 MediaStream（音频轨道）。 */
export async function acquireStream(kind: CaptureSourceKind): Promise<MediaStream> {
  const media = navigator.mediaDevices;
  if (!media) throw new Error("当前环境不支持媒体采集（navigator.mediaDevices 缺失）");

  if (kind === "microphone") {
    return media.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: true, channelCount: 1 }
    });
  }

  // browser_audio / screen_window / system_audio 均走屏幕/标签页共享并勾选音频。
  if (!media.getDisplayMedia) {
    throw new Error("当前环境不支持屏幕/标签页音频采集（getDisplayMedia 缺失）");
  }
  const stream = await media.getDisplayMedia({
    audio: { echoCancellation: false, noiseSuppression: false } as MediaTrackConstraints,
    video: true
  });
  if (stream.getAudioTracks().length === 0) {
    stream.getTracks().forEach((track) => track.stop());
    throw new Error("未捕获到音频轨道，请在共享时勾选“分享音频/系统音频”");
  }
  return stream;
}

/**
 * 启动采集：从已获取的 MediaStream 持续产出 16k PCM 帧。
 * 返回的 session.stop() 会停止采集、关闭轨道与 AudioContext。
 */
export async function startAudioCapture(
  stream: MediaStream,
  options: AudioCaptureOptions
): Promise<AudioCaptureSession> {
  const sampleRate = options.sampleRate ?? TARGET_SAMPLE_RATE;
  const frameSamples = Math.round((sampleRate * (options.frameMs ?? 100)) / 1000);

  const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const context = new AudioCtx({ sampleRate });
  if (context.state === "suspended") await context.resume();

  const blobUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
  let stopped = false;
  let pending: number[] = [];

  const flush = (force: boolean) => {
    while (pending.length >= frameSamples || (force && pending.length > 0)) {
      const slice = pending.slice(0, frameSamples);
      pending = pending.slice(frameSamples);
      const buffer = new Int16Array(slice);
      options.onChunk(buffer.buffer);
      if (force && pending.length === 0) break;
    }
  };

  try {
    await context.audioWorklet.addModule(blobUrl);
  } finally {
    URL.revokeObjectURL(blobUrl);
  }

  const source = context.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(context, "pcm-capture-processor");
  // 累积到 ~frameMs 再发，避免每 128 采样一帧造成 WS 风暴。
  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    if (stopped) return;
    const incoming = new Int16Array(event.data);
    for (let i = 0; i < incoming.length; i += 1) pending.push(incoming[i]);
    flush(false);
  };
  source.connect(node);
  // 接一个静音 gain 到 destination，保证 worklet 在所有浏览器里都被调度，且不外放。
  const sink = context.createGain();
  sink.gain.value = 0;
  node.connect(sink);
  sink.connect(context.destination);

  const handleTrackEnded = () => {
    if (!stopped) options.onEnded?.();
  };
  stream.getAudioTracks().forEach((track) => track.addEventListener("ended", handleTrackEnded));

  const stop = async () => {
    if (stopped) return;
    stopped = true;
    flush(true);
    try {
      node.port.onmessage = null;
      node.disconnect();
      source.disconnect();
      sink.disconnect();
    } catch {
      // 忽略断开时的竞态
    }
    stream.getTracks().forEach((track) => track.stop());
    try {
      await context.close();
    } catch {
      // 已关闭
    }
  };

  return { stop };
}
