import { describe, expect, it } from "vitest";
import { buildSessionPayload, toLanguageCode } from "./sessionPayload";
import type { FloatingFormState, QuickFormState, SourceInputState } from "../types/workflow";

const quickForm: QuickFormState = {
  name: "季度发布会",
  domain: "技术",
  sourceLanguage: "自动检测",
  targetLanguage: "中文",
  modelProfile: "高准确",
  source: "url",
  ttsEnabled: true,
  glossary: [{ sourceTerm: "latency", targetTerm: "延迟" }]
};

const floatingForm: FloatingFormState = {
  domain: "通用",
  sourceLanguage: "英语",
  targetLanguage: "中文",
  modelProfile: "智能默认",
  source: "system-audio",
  ttsEnabled: false,
  style: "双语字幕",
  size: "标准",
  opacity: "90%",
  captionPinned: false,
  captionOffsetY: 0
};

const emptyInput: SourceInputState = {
  fileName: "",
  url: "",
  permissionState: "idle",
  permissionMessage: ""
};

describe("session payload builder", () => {
  it("maps labels and copies quick-mode glossary terms", () => {
    const input = { ...emptyInput, url: " https://example.com/live " };
    const payload = buildSessionPayload("quick", quickForm, floatingForm, input, emptyInput);

    expect(toLanguageCode("自动检测")).toBe("auto");
    expect(payload).toMatchObject({
      inputMode: "url",
      sourceLanguage: "auto",
      targetLanguage: "zh",
      sourceUrl: "https://example.com/live",
      glossary: [{ sourceTerm: "latency", targetTerm: "延迟" }]
    });
    expect(payload.glossary).not.toBe(quickForm.glossary);
  });

  it("keeps floating payload independent of quick-only glossary", () => {
    const payload = buildSessionPayload("floating", quickForm, floatingForm, emptyInput, emptyInput);

    expect(payload).toMatchObject({
      inputMode: "system_audio",
      productMode: "floating",
      sessionName: "悬浮字幕",
      sourceLanguage: "en",
      targetLanguage: "zh"
    });
    expect(payload.glossary).toBeUndefined();
  });
});
