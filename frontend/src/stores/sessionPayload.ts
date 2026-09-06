import type { CreateSessionPayload } from "../api/client";
import type {
  FloatingFormState,
  GlossaryTerm,
  ProductMode,
  QuickFormState,
  SourceInputState
} from "../types/workflow";
import { videoFixtures } from "./sessionFixture";

const inputModeBySourceKey: Record<string, CreateSessionPayload["inputMode"]> = {
  ...Object.fromEntries(videoFixtures.map((fixture) => [fixture.key, "demo"] as const)),
  "video-file": "media_element_audio",
  "audio-file": "media_element_audio",
  url: "url",
  microphone: "microphone",
  "browser-tab": "browser_audio",
  "screen-window": "screen_window",
  "system-audio": "system_audio"
};

const languageCodeByLabel: Record<string, string> = {
  自动检测: "auto",
  英语: "en",
  中文: "zh",
  日语: "ja",
  韩语: "ko",
  法语: "fr",
  德语: "de"
};

export function toLanguageCode(label: string): string {
  return languageCodeByLabel[label] ?? label;
}

export function buildSessionPayload(
  mode: ProductMode,
  quickForm: QuickFormState,
  floatingForm: FloatingFormState,
  quickInput: SourceInputState,
  floatingInput: SourceInputState
): CreateSessionPayload {
  const form = mode === "quick" ? quickForm : floatingForm;
  const input = mode === "quick" ? quickInput : floatingInput;
  const sourceKey = form.source;
  const glossary: GlossaryTerm[] = mode === "quick" ? quickForm.glossary : [];

  return {
    inputMode: inputModeBySourceKey[sourceKey] ?? "demo",
    sourceLanguage: toLanguageCode(form.sourceLanguage),
    targetLanguage: toLanguageCode(form.targetLanguage),
    productMode: mode,
    sessionName: mode === "quick" ? quickForm.name : "悬浮字幕",
    domain: form.domain,
    modelProfile: form.modelProfile,
    sourceKey,
    sourceFileName: input.fileName || undefined,
    sourceUrl: sourceKey === "url" ? input.url.trim() : undefined,
    sourcePermission: input.permissionState,
    ttsEnabled: form.ttsEnabled,
    ...(glossary.length ? { glossary: glossary.map((term) => ({ ...term })) } : {})
  };
}
