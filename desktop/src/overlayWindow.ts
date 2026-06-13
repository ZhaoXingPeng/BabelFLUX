export async function setOverlayLocked(locked: boolean) {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setIgnoreCursorEvents(locked);
  } catch {
    // Browser preview has no Tauri window; keep it usable for UI development.
  }
}

export async function registerUnlockShortcut(onUnlock: () => void) {
  try {
    const { register, unregister } = await import("@tauri-apps/plugin-global-shortcut");
    const shortcut = "CommandOrControl+Shift+L";
    await register(shortcut, onUnlock);
    return () => unregister(shortcut);
  } catch {
    return () => undefined;
  }
}
