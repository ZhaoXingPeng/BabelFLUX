import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { AudioCaptureOptions, AudioCaptureSession } from "@frontend/composables/useAudioCapture";

interface NativeAudioChunk {
  data: string;
  sampleRate: number;
  channels: number;
  frameMs: number;
}

interface NativeAudioError {
  message: string;
}

export async function startNativeSystemAudioCapture(options: AudioCaptureOptions): Promise<AudioCaptureSession> {
  let stopped = false;
  const unlisteners: UnlistenFn[] = [];

  const cleanupListeners = () => {
    while (unlisteners.length > 0) {
      unlisteners.pop()?.();
    }
  };

  const stop = async (notifyEnded: boolean) => {
    if (stopped) return;
    stopped = true;
    cleanupListeners();
    try {
      await invoke("stop_windows_loopback_capture");
    } catch {
      // The native side may already be stopped after an error.
    }
    if (notifyEnded) options.onEnded?.();
  };

  unlisteners.push(
    await listen<NativeAudioChunk>("native-audio-chunk", (event) => {
      if (stopped) return;
      try {
        options.onChunk(base64ToArrayBuffer(event.payload.data));
      } catch {
        options.onError?.("Windows 系统音频数据解析失败");
        void stop(true);
      }
    })
  );

  unlisteners.push(
    await listen<NativeAudioError>("native-audio-error", (event) => {
      if (stopped) return;
      options.onError?.(event.payload.message);
      void stop(true);
    })
  );

  try {
    await invoke("start_windows_loopback_capture");
  } catch (error) {
    cleanupListeners();
    throw new Error(error instanceof Error ? error.message : String(error));
  }

  return {
    stop: () => stop(false)
  };
}

function base64ToArrayBuffer(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}
