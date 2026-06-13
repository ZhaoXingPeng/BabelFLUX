import { describe, expect, it } from "vitest";
import { describeMediaError } from "./useAudioCapture";

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
