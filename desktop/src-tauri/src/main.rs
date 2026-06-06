#![cfg_attr(all(target_os = "windows", not(debug_assertions)), windows_subsystem = "windows")]

use tauri::{Emitter, Manager};

mod audio_capture;
mod native_drag;

const DEEP_LINK_SCHEME: &str = "lingosync://";

fn find_deep_link(argv: &[String]) -> Option<String> {
    argv.iter().find_map(|arg| {
        let trimmed = arg.trim().trim_matches(|ch| ch == '"' || ch == '\'');
        let start = trimmed.find(DEEP_LINK_SCHEME)?;
        Some(
            trimmed[start..]
                .trim_matches(|ch| ch == '"' || ch == '\'')
                .to_string(),
        )
    })
}

#[tauri::command]
fn exit_overlay_app(app: tauri::AppHandle) {
    app.exit(0);
}

fn main() {
    tauri::Builder::default()
        .manage(audio_capture::AudioCaptureState::default())
        .invoke_handler(tauri::generate_handler![
            audio_capture::start_windows_loopback_capture,
            audio_capture::stop_windows_loopback_capture,
            exit_overlay_app
        ])
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            if let Some(window) = app.get_webview_window("overlay") {
                let _ = window.show();
                let _ = window.set_focus();
            }

            if let Some(url) = find_deep_link(&argv) {
                let _ = app.emit("deep-link-url", url.clone());
                if let Some(window) = app.get_webview_window("overlay") {
                    let _ = window.emit("deep-link-url", url);
                }
            }
        }))
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_store::Builder::new().build())
        .setup(|app| {
            if let Some(window) = app.get_webview_window("overlay") {
                let _ = window.set_decorations(false);
                let _ = window.set_always_on_top(true);
                let _ = window.set_skip_taskbar(true);
                let _ = window.set_shadow(false);
                let _ = native_drag::install_overlay_drag_region(&window);
                let _ = window.show();
            }

            #[cfg(any(target_os = "linux", all(target_os = "windows", not(debug_assertions))))]
            {
                use tauri_plugin_deep_link::DeepLinkExt;
                let _ = app.deep_link().register_all();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running LingoSync desktop overlay");
}
