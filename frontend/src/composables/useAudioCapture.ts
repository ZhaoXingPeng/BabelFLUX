/**
 * 浏览器/WebView 音频采集 → 16kHz 单声道 s16le PCM 帧流。
 *
 * 用于「实时采集」类音源（麦克风 / 浏览器标签页 / 屏幕或窗口 / 系统音频），
 * 把采集到的音频降采样为后端 LiveTranslate 所需的 16k 单声道 PCM，按 ~40ms
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
  /** 收到一帧 16k 单声道 s16le PCM（ArrayBuffer，约 40ms）时回调。 */
  onChunk: (chunk: ArrayBuffer) => void;
  /** 采集异常（设备被拔出 / 轨道结束 / 权限撤销）。 */
  onError?: (message: string) => void;
  /** 用户在系统选择器里结束共享（轨道 ended）时回调。 */
  onEnded?: () => void;
  /** 目标采样率，默认 16000。 */
  sampleRate?: number;
  /** 分帧时长（ms），默认 40ms。 */
  frameMs?: number;
}

export interface AudioCaptureSession {
  stop: () => Promise<void>;
}

const TARGET_SAMPLE_RATE = 16000;
const LOW_LATENCY_FRAME_MS = 40;

export interface MediaElementClock {
  playbackMs: number;
  sentAudioMs: number;
}

export interface MediaElementAudioCaptureOptions extends AudioCaptureOptions {
  /** 媒体元素播放时钟与已发送音频时钟，用于前后端同步观测。 */
  onClock?: (clock: MediaElementClock) => void;
}

function audioContextCtor() {
  return window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
}

type ExtendedDisplayMediaOptions = DisplayMediaStreamOptions & {
  monitorTypeSurfaces?: "include" | "exclude";
  preferCurrentTab?: boolean;
  selfBrowserSurface?: "include" | "exclude";
  surfaceSwitching?: "include" | "exclude";
  systemAudio?: "include" | "exclude";
  windowAudio?: "exclude" | "window" | "system";
};

function buildDisplayMediaOptions(kind: CaptureSourceKind): ExtendedDisplayMediaOptions {
  const audio: MediaTrackConstraints = {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1
  };
  const common: ExtendedDisplayMediaOptions = {
    audio,
    video: true,
    selfBrowserSurface: "exclude",
    surfaceSwitching: "include"
  };

  if (kind === "browser_audio") {
    return {
      ...common,
      monitorTypeSurfaces: "exclude",
      preferCurrentTab: false,
      systemAudio: "exclude",
      windowAudio: "exclude"
    };
  }

  if (kind === "screen_window") {
    return {
      ...common,
      monitorTypeSurfaces: "include",
      systemAudio: "include",
      windowAudio: "window"
    };
  }

  return {
    ...common,
    monitorTypeSurfaces: "include",
    systemAudio: "include",
    windowAudio: "system"
  };
}

function stopStream(stream: MediaStream) {
  stream.getTracks().forEach((track) => track.stop());
}

function validateDisplayStream(kind: CaptureSourceKind, stream: MediaStream) {
  const audioTracks = stream.getAudioTracks();
  const videoTrack = stream.getVideoTracks()[0];
  const displaySurface = (videoTrack?.getSettings() as MediaTrackSettings & { displaySurface?: string }).displaySurface;

  if (kind === "browser_audio" && displaySurface && displaySurface !== "browser") {
    stopStream(stream);
    throw new Error("标签页音频需要在共享窗口中选择“标签页”，并勾选“分享标签页音频”。");
  }

  if (audioTracks.length === 0) {
    stopStream(stream);
    if (kind === "browser_audio") {
      throw new Error("未捕获到标签页音频，请选择“标签页”并勾选“分享标签页音频”。");
    }
    if (kind === "screen_window") {
      throw new Error("未捕获到屏幕/窗口音频，请选择可分享音频的屏幕或窗口，并勾选共享音频。");
    }
    throw new Error("未捕获到系统音频轨道，请选择整个屏幕并勾选共享系统音频。");
  }
}

/** 把浏览器/WebView 的媒体异常翻成对症的、可操作的中文提示（区分权限被拒/无设备/被占用/用户取消）。 */
export function describeMediaError(kind: CaptureSourceKind, error: unknown): Error {
  const name = error instanceof DOMException ? error.name : "";
  const label =
    kind === "microphone"
      ? "麦克风"
      : kind === "browser_audio"
        ? "标签页音频"
        : kind === "screen_window"
          ? "屏幕 / 窗口"
          : "系统音频";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return new Error(
        kind === "microphone"
          ? "麦克风权限被拒绝。请在 Windows「设置 → 隐私和安全性 → 麦克风」中允许桌面应用访问，或在浏览器允许麦克风后重试。"
          : `${label}共享被拒绝或取消。请在弹出的共享窗口中选择来源并勾选「共享音频」后重试。`
      );
    case "NotFoundError":
    case "DevicesNotFoundError":
      return new Error(`未找到可用的${label}设备，请检查设备连接与系统输入/输出设置。`);
    case "NotReadableError":
    case "TrackStartError":
      return new Error(`${label}设备被其他程序占用，请关闭占用它的程序后重试。`);
    case "AbortError":
      return new Error("已取消音源选择，可重新选择音源后开始。");
    default:
      return error instanceof Error ? error : new Error(`${label}采集启动失败，请重试或更换音源。`);
  }
}

/** 按音源种类获取浏览器 MediaStream（音频轨道）。 */
export async function acquireStream(kind: CaptureSourceKind): Promise<MediaStream> {
  const media = navigator.mediaDevices;
  if (!media) throw new Error("当前环境不支持媒体采集（navigator.mediaDevices 缺失）");

  if (kind === "microphone") {
    try {
      return await media.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: true, channelCount: 1 }
      });
    } catch (error) {
      throw describeMediaError(kind, error);
    }
  }

  // browser_audio / screen_window / system_audio 均走屏幕/标签页共享并勾选音频。
  if (!media.getDisplayMedia) {
    throw new Error("当前环境不支持屏幕/标签页音频采集（getDisplayMedia 缺失）");
  }
  try {
    const stream = await media.getDisplayMedia(buildDisplayMediaOptions(kind));
    validateDisplayStream(kind, stream);
    return stream;
  } catch (error) {
    throw describeMediaError(kind, error);
  }
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
  const frameSamples = Math.round((sampleRate * (options.frameMs ?? LOW_LATENCY_FRAME_MS)) / 1000);

  const AudioCtx = audioContextCtor();
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

/**
 * 从正在播放的 <video>/<audio> 元素直接采集音频并推成 16k PCM。
 *
 * 上传视频实时同传使用这条路径：用户看到/听到的媒体元素就是模型输入源，
 * 避免“前端播放 blob、后端另起 ffmpeg 解码文件”形成双时钟。
 */
export async function startMediaElementAudioCapture(
  element: HTMLMediaElement,
  options: MediaElementAudioCaptureOptions
): Promise<AudioCaptureSession> {
  const sampleRate = options.sampleRate ?? TARGET_SAMPLE_RATE;
  const frameSamples = Math.round((sampleRate * (options.frameMs ?? LOW_LATENCY_FRAME_MS)) / 1000);
  const AudioCtx = audioContextCtor();
  const context = new AudioCtx({ sampleRate });
  if (context.state === "suspended") await context.resume();

  const blobUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
  let stopped = false;
  let pending: number[] = [];
  let sentSamples = 0;
  let lastClockAt = 0;

  const emitClock = (force = false) => {
    if (!options.onClock) return;
    const now = performance.now();
    if (!force && now - lastClockAt < 250) return;
    lastClockAt = now;
    options.onClock({
      playbackMs: Math.max(0, Math.round(element.currentTime * 1000)),
      sentAudioMs: Math.round((sentSamples / sampleRate) * 1000)
    });
  };

  const flush = (force: boolean) => {
    while (pending.length >= frameSamples || (force && pending.length > 0)) {
      const slice = pending.slice(0, frameSamples);
      pending = pending.slice(frameSamples);
      const buffer = new Int16Array(slice);
      sentSamples += slice.length;
      options.onChunk(buffer.buffer);
      emitClock(force);
      if (force && pending.length === 0) break;
    }
  };

  try {
    await context.audioWorklet.addModule(blobUrl);
  } finally {
    URL.revokeObjectURL(blobUrl);
  }

  const source = context.createMediaElementSource(element);
  const node = new AudioWorkletNode(context, "pcm-capture-processor");
  const sink = context.createGain();
  sink.gain.value = 0;

  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    if (stopped || element.paused || element.ended) return;
    const incoming = new Int16Array(event.data);
    for (let i = 0; i < incoming.length; i += 1) pending.push(incoming[i]);
    flush(false);
  };

  const resumeContext = () => {
    if (context.state === "suspended") void context.resume();
  };
  const handleEnded = () => {
    if (!stopped) options.onEnded?.();
  };
  element.addEventListener("play", resumeContext);
  element.addEventListener("ended", handleEnded);

  source.connect(context.destination);
  source.connect(node);
  node.connect(sink);
  sink.connect(context.destination);

  const stop = async () => {
    if (stopped) return;
    stopped = true;
    flush(true);
    emitClock(true);
    element.removeEventListener("play", resumeContext);
    element.removeEventListener("ended", handleEnded);
    try {
      node.port.onmessage = null;
      node.disconnect();
      sink.disconnect();
      source.disconnect();
    } catch {
      // 忽略断开时的竞态
    }
    try {
      await context.close();
    } catch {
      // 已关闭
    }
  };

  return { stop };
}
