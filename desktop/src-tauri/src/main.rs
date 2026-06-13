#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

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

// 悬浮窗是透明无边框置顶窗口，WebView2 默认的权限气泡在此类窗口上几乎无法交互，
// 会导致「麦克风」音源的 getUserMedia 卡在等待授权而静默失败。这里在宿主侧注册
// PermissionRequested 处理器，对麦克风/摄像头直接放行 —— 符合 Windows/WebView2
// 桌面应用「由宿主决定媒体权限」的最佳实践，用户选麦克风即可一次成功、无需弹窗。
// 系统音频走原生 WASAPI loopback（见 audio_capture.rs），不经过 WebView2，本就无需授权。
#[cfg(target_os = "windows")]
fn grant_overlay_media_permissions(window: &tauri::WebviewWindow) {
    use webview2_com::Microsoft::Web::WebView2::Win32::{
        COREWEBVIEW2_PERMISSION_KIND, COREWEBVIEW2_PERMISSION_KIND_CAMERA,
        COREWEBVIEW2_PERMISSION_KIND_MICROPHONE, COREWEBVIEW2_PERMISSION_STATE_ALLOW,
    };
    use webview2_com::PermissionRequestedEventHandler;

    let _ = window.with_webview(|webview| unsafe {
        let core = match webview.controller().CoreWebView2() {
            Ok(core) => core,
            Err(_) => return,
        };
        let mut token = Default::default();
        let _ = core.add_PermissionRequested(
            &PermissionRequestedEventHandler::create(Box::new(|_, args| {
                let Some(args) = args else { return Ok(()) };
                let mut kind = COREWEBVIEW2_PERMISSION_KIND::default();
                args.PermissionKind(&mut kind)?;
                if kind == COREWEBVIEW2_PERMISSION_KIND_MICROPHONE
                    || kind == COREWEBVIEW2_PERMISSION_KIND_CAMERA
                {
                    args.SetState(COREWEBVIEW2_PERMISSION_STATE_ALLOW)?;
                }
                Ok(())
            })),
            &mut token,
        );
    });
}

#[cfg(not(target_os = "windows"))]
fn grant_overlay_media_permissions(_window: &tauri::WebviewWindow) {}

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
                // 宿主侧放行麦克风/摄像头，让悬浮窗内麦克风音源 getUserMedia 免弹窗直通。
                grant_overlay_media_permissions(&window);
            }

            // Windows 下 debug 构建同样注册 lingosync:// scheme，否则 `tauri dev` 期间
            // 无法验证「激活客户端」的 deep-link 唤起（历史上的唤不起问题之一）。
            #[cfg(any(target_os = "linux", target_os = "windows"))]
            {
                use tauri_plugin_deep_link::DeepLinkExt;
                let _ = app.deep_link().register_all();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running BabelFlux desktop overlay");
}
