import type { FloatingFormState } from "@frontend/types/workflow";

const STORAGE_KEY = "lingosync.desktop.overlay";

export interface OverlaySettings {
  form: FloatingFormState;
  locked: boolean;
  opacity: number;
}

export const defaultOverlaySettings: OverlaySettings = {
  locked: false,
  opacity: 0.94,
  form: {
    domain: "通用",
    sourceLanguage: "自动检测",
    targetLanguage: "中文",
    modelProfile: "快速低延迟",
    source: "system-audio",
    style: "双语字幕",
    size: "标准",
    opacity: "90%",
    captionPinned: false,
    captionOffsetY: 0
  }
};

export function loadOverlaySettings(): OverlaySettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...defaultOverlaySettings, ...JSON.parse(raw) } : defaultOverlaySettings;
  } catch {
    return defaultOverlaySettings;
  }
}

export function saveOverlaySettings(settings: OverlaySettings) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}
