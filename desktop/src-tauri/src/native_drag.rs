#[cfg(target_os = "windows")]
pub fn install_overlay_drag_region(window: &tauri::WebviewWindow) -> Result<(), String> {
    windows_impl::install(window)
}

#[cfg(not(target_os = "windows"))]
pub fn install_overlay_drag_region(_window: &tauri::WebviewWindow) -> Result<(), String> {
    Ok(())
}

#[cfg(target_os = "windows")]
mod windows_impl {
    use tauri::WebviewWindow;
    use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, RECT, WPARAM};
    use windows::Win32::UI::Shell::{DefSubclassProc, SetWindowSubclass};
    use windows::Win32::UI::WindowsAndMessaging::{GetWindowRect, HTCLIENT, WM_NCHITTEST};

    const OVERLAY_SUBCLASS_ID: usize = 0x4c53_4452; // LSDR

    pub fn install(window: &WebviewWindow) -> Result<(), String> {
        let hwnd = window
            .hwnd()
            .map_err(|error| format!("获取悬浮窗 HWND 失败：{error}"))?;
        let ok = unsafe {
            SetWindowSubclass(
                HWND(hwnd.0 as _),
                Some(overlay_subclass_proc),
                OVERLAY_SUBCLASS_ID,
                0,
            )
        };
        if ok.as_bool() {
            Ok(())
        } else {
            Err("安装 Windows 原生拖拽区域失败".to_string())
        }
    }

    unsafe extern "system" fn overlay_subclass_proc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
        _subclass_id: usize,
        _ref_data: usize,
    ) -> LRESULT {
        if msg == WM_NCHITTEST {
            if let Some(hit) = hit_test_overlay(hwnd, lparam) {
                return hit;
            }
        }
        unsafe { DefSubclassProc(hwnd, msg, wparam, lparam) }
    }

    fn hit_test_overlay(hwnd: HWND, lparam: LPARAM) -> Option<LRESULT> {
        let mut rect = RECT::default();
        unsafe { GetWindowRect(hwnd, &mut rect).ok()? };
        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        if width <= 0 || height <= 0 {
            return None;
        }

        let screen_x = signed_low_word(lparam.0);
        let screen_y = signed_high_word(lparam.0);
        let x = screen_x - rect.left;
        let y = screen_y - rect.top;
        if x < 0 || y < 0 || x > width || y > height {
            return None;
        }

        // Keep every pixel in the WebView client area so Vue receives button
        // clicks reliably. Window dragging is handled in App.vue, where form
        // controls and caption actions can be excluded with DOM-level checks.
        Some(LRESULT(HTCLIENT as isize))
    }

    fn signed_low_word(value: isize) -> i32 {
        ((value & 0xffff) as u16 as i16) as i32
    }

    fn signed_high_word(value: isize) -> i32 {
        (((value >> 16) & 0xffff) as u16 as i16) as i32
    }
}
