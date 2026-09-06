import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import FloatingCaption from "./FloatingCaption.vue";
import type { FloatingFormState, TranscriptPair } from "../workflow/types";

function baseForm(): FloatingFormState {
  return {
    domain: "通用",
    sourceLanguage: "英语",
    targetLanguage: "中文",
    modelProfile: "快速低延迟",
    source: "system-audio",
    ttsEnabled: false,
    style: "双语字幕",
    size: "标准",
    opacity: "90%",
    captionPinned: false,
    captionOffsetY: 0
  };
}

const pair: TranscriptPair = {
  segmentId: "s1",
  time: "00:01",
  source: "Hello world.",
  translation: "你好，世界。",
  state: "partial",
  isActive: true
};

describe("FloatingCaption close confirmation", () => {
  it("emits close from the caption toolbar and renders the embedded confirmation", async () => {
    const wrapper = mount(FloatingCaption, {
      props: {
        pair,
        form: baseForm(),
        desktop: true,
        status: { status: "syncing", lagMs: 0, message: "LIVE" }
      }
    });

    await wrapper.get('button[aria-label="关闭悬浮字幕"]').trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);

    await wrapper.setProps({ closeConfirmOpen: true });
    expect(wrapper.find(".floating-close-confirm").exists()).toBe(true);
    expect(wrapper.text()).toContain("报告历史");
  });

  it("keeps cancellation and confirmation as explicit separate events", async () => {
    const wrapper = mount(FloatingCaption, {
      props: {
        pair,
        form: baseForm(),
        desktop: true,
        closeConfirmOpen: true
      }
    });

    const buttons = wrapper.findAll(".floating-close-actions button");
    await buttons[0].trigger("click");
    await buttons[1].trigger("click");

    expect(wrapper.emitted("cancelClose")).toHaveLength(1);
    expect(wrapper.emitted("confirmClose")).toHaveLength(1);
  });

  it("does not mark the caption panel as a native drag region", () => {
    const wrapper = mount(FloatingCaption, {
      props: {
        pair,
        form: baseForm(),
        desktop: true,
        closeConfirmOpen: true
      }
    });

    expect(wrapper.attributes("data-tauri-drag-region")).toBeUndefined();
    expect(wrapper.find(".floating-source").attributes("data-tauri-drag-region")).toBeUndefined();
    expect(wrapper.find(".floating-translation").attributes("data-tauri-drag-region")).toBeUndefined();
  });
});
