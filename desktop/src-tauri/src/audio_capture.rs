use std::sync::{mpsc, Mutex};
use std::thread::JoinHandle;

use tauri::{AppHandle, State};

#[derive(Default)]
pub struct AudioCaptureState {
    worker: Mutex<Option<CaptureWorker>>,
}

struct CaptureWorker {
    stop_tx: mpsc::Sender<()>,
    join: JoinHandle<()>,
}

impl CaptureWorker {
    fn stop(self) {
        let _ = self.stop_tx.send(());
        let _ = self.join.join();
    }
}

#[tauri::command]
pub fn start_windows_loopback_capture(
    app: AppHandle,
    state: State<'_, AudioCaptureState>,
) -> Result<(), String> {
    let previous = state
        .worker
        .lock()
        .map_err(|_| "音频采集状态锁定失败".to_string())?
        .take();
    if let Some(worker) = previous {
        worker.stop();
    }

    let worker = CaptureWorker::start(app)?;
    *state
        .worker
        .lock()
        .map_err(|_| "音频采集状态锁定失败".to_string())? = Some(worker);
    Ok(())
}

#[tauri::command]
pub fn stop_windows_loopback_capture(state: State<'_, AudioCaptureState>) -> Result<(), String> {
    let worker = state
        .worker
        .lock()
        .map_err(|_| "音频采集状态锁定失败".to_string())?
        .take();
    if let Some(worker) = worker {
        worker.stop();
    }
    Ok(())
}

#[cfg(target_os = "windows")]
mod platform {
    use std::collections::VecDeque;
    use std::sync::mpsc;

    use base64::engine::general_purpose::STANDARD;
    use base64::Engine;
    use serde::Serialize;
    use tauri::{AppHandle, Emitter};
    use wasapi::{
        deinitialize, initialize_mta, DeviceEnumerator, Direction, SampleType, StreamMode,
        WaveFormat,
    };

    use super::CaptureWorker;

    const TARGET_SAMPLE_RATE: usize = 16_000;
    const TARGET_CHANNELS: usize = 1;
    const TARGET_FRAME_MS: usize = 100;
    const TARGET_FRAME_BYTES: usize = TARGET_SAMPLE_RATE * TARGET_FRAME_MS / 1000 * 2;

    #[derive(Clone, Serialize)]
    #[serde(rename_all = "camelCase")]
    struct NativeAudioChunk {
        data: String,
        sample_rate: usize,
        channels: usize,
        frame_ms: usize,
    }

    #[derive(Clone, Serialize)]
    struct NativeAudioError {
        message: String,
    }

    impl CaptureWorker {
        pub(super) fn start(app: AppHandle) -> Result<Self, String> {
            let (stop_tx, stop_rx) = mpsc::channel();
            let join = std::thread::Builder::new()
                .name("lingosync-windows-loopback".to_string())
                .spawn(move || {
                    if let Err(message) = run_loopback_capture(app.clone(), stop_rx) {
                        let _ = app.emit("native-audio-error", NativeAudioError { message });
                    }
                })
                .map_err(|error| format!("启动 Windows 系统音频采集线程失败：{error}"))?;

            Ok(Self { stop_tx, join })
        }
    }

    fn run_loopback_capture(app: AppHandle, stop_rx: mpsc::Receiver<()>) -> Result<(), String> {
        initialize_mta()
            .ok()
            .map_err(|error| format!("初始化 Windows 音频服务失败：{error}"))?;
        let result = run_loopback_capture_inner(app, stop_rx);
        deinitialize();
        result
    }

    fn run_loopback_capture_inner(
        app: AppHandle,
        stop_rx: mpsc::Receiver<()>,
    ) -> Result<(), String> {
        let enumerator =
            DeviceEnumerator::new().map_err(|error| format!("获取 Windows 音频设备失败：{error}"))?;
        let device = enumerator
            .get_default_device(&Direction::Render)
            .map_err(|error| format!("未找到 Windows 默认播放设备：{error}"))?;
        let mut audio_client = device
            .get_iaudioclient()
            .map_err(|error| format!("创建 Windows 音频客户端失败：{error}"))?;

        let desired_format = WaveFormat::new(
            16,
            16,
            &SampleType::Int,
            TARGET_SAMPLE_RATE,
            TARGET_CHANNELS,
            None,
        );
        let (_default_period, min_period) = audio_client
            .get_device_period()
            .map_err(|error| format!("读取 Windows 音频设备周期失败：{error}"))?;
        let mode = StreamMode::EventsShared {
            autoconvert: true,
            buffer_duration_hns: min_period,
        };
        audio_client
            .initialize_client(&desired_format, &Direction::Capture, &mode)
            .map_err(|error| format!("初始化 Windows 系统音频 loopback 失败：{error}"))?;
        let event_handle = audio_client
            .set_get_eventhandle()
            .map_err(|error| format!("创建 Windows 音频事件句柄失败：{error}"))?;
        let capture_client = audio_client
            .get_audiocaptureclient()
            .map_err(|error| format!("创建 Windows 音频采集客户端失败：{error}"))?;

        let mut sample_queue = VecDeque::with_capacity(TARGET_FRAME_BYTES * 4);
        audio_client
            .start_stream()
            .map_err(|error| format!("启动 Windows 系统音频采集失败：{error}"))?;

        loop {
            if stop_rx.try_recv().is_ok() {
                break;
            }

            let next_frames = capture_client
                .get_next_packet_size()
                .map_err(|error| format!("读取 Windows 音频包大小失败：{error}"))?
                .unwrap_or(0);
            if next_frames > 0 {
                capture_client
                    .read_from_device_to_deque(&mut sample_queue)
                    .map_err(|error| format!("读取 Windows 系统音频失败：{error}"))?;
            }

            while sample_queue.len() >= TARGET_FRAME_BYTES {
                let mut chunk = vec![0u8; TARGET_FRAME_BYTES];
                for byte in chunk.iter_mut() {
                    *byte = sample_queue.pop_front().unwrap_or(0);
                }
                emit_chunk(&app, chunk)?;
            }

            if stop_rx.try_recv().is_ok() {
                break;
            }
            let _ = event_handle.wait_for_event(200);
        }

        let _ = audio_client.stop_stream();
        Ok(())
    }

    fn emit_chunk(app: &AppHandle, chunk: Vec<u8>) -> Result<(), String> {
        app.emit(
            "native-audio-chunk",
            NativeAudioChunk {
                data: STANDARD.encode(chunk),
                sample_rate: TARGET_SAMPLE_RATE,
                channels: TARGET_CHANNELS,
                frame_ms: TARGET_FRAME_MS,
            },
        )
        .map_err(|error| format!("发送 Windows 系统音频数据失败：{error}"))
    }
}

#[cfg(not(target_os = "windows"))]
mod platform {
    use tauri::AppHandle;

    use super::CaptureWorker;

    impl CaptureWorker {
        pub(super) fn start(_app: AppHandle) -> Result<Self, String> {
            Err("原生系统音频采集当前仅支持 Windows".to_string())
        }
    }
}
