import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StreamLine from "./StreamLine.vue";

describe("StreamLine", () => {
  it("已定稿的句子渲染为纯文本，不带逐字 token 与光标（不会被反复重挂载）", () => {
    const wrapper = mount(StreamLine, { props: { text: "这是一句已定稿的中文字幕", state: "final" } });
    expect(wrapper.findAll(".stream-token")).toHaveLength(0);
    expect(wrapper.find(".stream-caret").exists()).toBe(false);
    expect(wrapper.text()).toContain("这是一句已定稿的中文字幕");
  });

  it("识别中的中文按「字」切分为独立 token，并显示流式光标", () => {
    const wrapper = mount(StreamLine, { props: { text: "你好世界", state: "partial" } });
    // 中文无空格：旧实现会整句一个 token → 每次更新整行重放动画。现在每个汉字一个 token。
    expect(wrapper.findAll(".stream-token")).toHaveLength(4);
    expect(wrapper.find(".stream-caret").exists()).toBe(true);
    expect(wrapper.text()).toContain("你好世界");
  });

  it("识别中的拉丁文按「词」切分，空白单独成块", () => {
    const wrapper = mount(StreamLine, { props: { text: "hello world", state: "partial" } });
    expect(wrapper.findAll(".stream-token")).toHaveLength(2);
    expect(wrapper.findAll(".stream-space")).toHaveLength(1);
  });

  it("中英混排：汉字逐字、英文单词整体", () => {
    const wrapper = mount(StreamLine, { props: { text: "你好 world", state: "partial" } });
    // 你 / 好 / world = 3 个 token；中间一个空白
    expect(wrapper.findAll(".stream-token")).toHaveLength(3);
    expect(wrapper.findAll(".stream-space")).toHaveLength(1);
  });
});
