export interface LaunchParams {
  sessionId?: string;
  source?: string;
  sourceLanguage?: string;
  targetLanguage?: string;
  displayMode?: "bilingual" | "translation-only" | "floating" | "compact";
  token?: string;
}

export function parseLaunchParams(rawUrl = window.location.href): LaunchParams {
  const url = new URL(rawUrl);
  const params = url.searchParams;
  return {
    sessionId: params.get("sessionId") ?? undefined,
    source: params.get("source") ?? undefined,
    sourceLanguage: params.get("sourceLanguage") ?? undefined,
    targetLanguage: params.get("targetLanguage") ?? undefined,
    displayMode: (params.get("displayMode") as LaunchParams["displayMode"]) ?? "bilingual",
    token: params.get("token") ?? undefined
  };
}

export async function listenForDeepLinks(handler: (params: LaunchParams) => void) {
  try {
    const { onOpenUrl } = await import("@tauri-apps/plugin-deep-link");
    return onOpenUrl((urls) => {
      const latest = urls.at(-1);
      if (latest) handler(parseLaunchParams(latest));
    });
  } catch {
    return () => undefined;
  }
}

export async function getLaunchDeepLink(): Promise<LaunchParams | null> {
  try {
    const { getCurrent } = await import("@tauri-apps/plugin-deep-link");
    const urls = await getCurrent();
    const latest = urls?.at(-1);
    return latest ? parseLaunchParams(latest) : null;
  } catch {
    return null;
  }
}
