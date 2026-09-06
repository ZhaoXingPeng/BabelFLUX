import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import GlossaryEditor from "./GlossaryEditor.vue";

describe("GlossaryEditor", () => {
  it("adds a trimmed source and target term", async () => {
    const wrapper = mount(GlossaryEditor, { props: { modelValue: [] } });

    await wrapper.get('[data-testid="glossary-source"]').setValue(" Transformer ");
    await wrapper.get('[data-testid="glossary-target"]').setValue(" 变压器 ");
    await wrapper.get('[aria-label="添加术语"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")).toEqual([[ [{ sourceTerm: "Transformer", targetTerm: "变压器" }] ]]);
  });

  it("does not add duplicate terms and can remove an existing term", async () => {
    const wrapper = mount(GlossaryEditor, {
      props: {
        modelValue: [{ sourceTerm: "latency", targetTerm: "延迟" }]
      }
    });

    await wrapper.get('[data-testid="glossary-source"]').setValue("latency");
    await wrapper.get('[data-testid="glossary-target"]').setValue("延迟");
    await wrapper.get('[aria-label="添加术语"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.text()).toContain("该术语已存在");

    await wrapper.get('[aria-label="删除术语 latency"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[ [] ]]);
  });

  it("ignores incomplete terms", async () => {
    const wrapper = mount(GlossaryEditor, { props: { modelValue: [] } });

    await wrapper.get('[data-testid="glossary-source"]').setValue("only-source");
    await wrapper.get('[aria-label="添加术语"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.text()).toContain("请填写原文和译法");
  });
});
