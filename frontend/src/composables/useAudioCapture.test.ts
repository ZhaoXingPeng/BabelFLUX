import { afterEach, describe, expect, it, vi } from "vitest";
import { describeMediaError, startAudioCapture } from "./useAudioCapture";

const originalAudioContext = window.AudioContext;
const originalAudioWorkletNode = globalThis.AudioWorkletNode;

afterEach(() => {
  Object.defineProperty(window, "AudioContext", {
    configurable: true,
    value: originalAudioContext
  });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: originalAudioWorkletNode
  });
  vi.restoreAllMocks();
});

function installAudioCaptureDoubles() {
  const close = vi.fn(async () => undefined);
  class FakeAudioContext {
    state = "running";
    destination = {};
    audioWorklet = { addModule: vi.fn(async () => undefined) };

    createMediaStreamSource() {
      return { connect: vi.fn(), disconnect: vi.fn() };
    }

    createGain() {
      return { gain: { value: 0 }, connect: vi.fn(), disconnect: vi.fn() };
    }

    close = close;
  }
  class FakeAudioWorkletNode {
    port = { onmessage: null as ((event: MessageEvent<ArrayBuffer>) => void) | null };
    connect = vi.fn();
    disconnect = vi.fn();
  }
  Object.defineProperty(window, "AudioContext", {
    configurable: true,
    value: FakeAudioContext
  });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: FakeAudioWorkletNode
  });
  return { close };
}

describe("describeMediaError", () => {
  it("麦克风权限被拒 → 指引到 Windows 隐私设置", () => {
    const message = describeMediaError("microphone", new DOMException("denied", "NotAllowedError")).message;
    expect(message).toContain("麦克风权限被拒绝");
    expect(message).toContain("隐私");
  });

  it("屏幕/标签页共享被拒 → 指引重新选择来源并勾选共享音频", () => {
    const message = describeMediaError("system_audio", new DOMException("denied", "NotAllowedError")).message;
    expect(message).toContain("被拒绝或取消");
    expect(message).toContain("共享音频");
  });

  it("无可用设备 / 设备被占用 给出对症提示", () => {
    expect(describeMediaError("microphone", new DOMException("none", "NotFoundError")).message).toContain("未找到");
    expect(describeMediaError("microphone", new DOMException("busy", "NotReadableError")).message).toContain("占用");
  });

  it("用户取消选择 → 友好提示而非报错", () => {
    expect(describeMediaError("screen_window", new DOMException("abort", "AbortError")).message).toContain("已取消");
  });

  it("非 DOMException 的普通错误原样透传（如校验类错误）", () => {
    const original = new Error("未捕获到系统音频轨道");
    expect(describeMediaError("system_audio", original)).toBe(original);
  });
});

describe("startAudioCapture", () => {
  it("停止采集时移除轨道结束监听器并且只清理一次", async () => {
    const { close } = installAudioCaptureDoubles();
    const track = {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      stop: vi.fn()
    };
    const stream = {
      getAudioTracks: () => [track],
      getTracks: () => [track]
    } as unknown as MediaStream;

    const session = await startAudioCapture(stream, {
      onChunk: vi.fn(),
      onEnded: vi.fn()
    });
    const endedHandler = track.addEventListener.mock.calls[0]?.[1];

    await session.stop();
    await session.stop();

    expect(endedHandler).toBeTypeOf("function");
    expect(track.removeEventListener).toHaveBeenCalledWith("ended", endedHandler);
    expect(track.removeEventListener).toHaveBeenCalledTimes(1);
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
  });
});
