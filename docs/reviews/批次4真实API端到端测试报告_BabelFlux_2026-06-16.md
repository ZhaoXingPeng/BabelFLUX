# BabelFlux 批次 4 真实 API 端到端测试报告

日期：2026-06-16
分支：`feat/tts-bilingual-playback`
测试目标：验证批次 3 TTS 在真实 DashScope LiveTranslate 链路中的音频事件、采样率、报告生成与字幕质量。

## 测试环境

- DashScope API Key：已从 `/hy-tmp/模型调用/默认业务空间-apiKey-5489798.csv` 配置到本地 `.env`，未提交。
- Workspace：使用 CSV 中的 `workspaceId=ws-axv6izbvdotqwbtk`。首次误用数字 `id=5489798` 时，实时翻译 WebSocket 返回 `Workspace access denied`。
- 后端：`MODEL_PROVIDER=real`
- 测试视频：`https://img.naixiai.cn/2026/06/05/ted_Unknown.mp4`
- 服务：`uvicorn app.main:app --host 127.0.0.1 --port 8000`

## 脚本修正

更新 `backend/scripts/e2e_online_url.py`：

- 创建 session 时传入 `ttsEnabled=true`，确保真实链路请求音频输出。
- WebSocket 地址携带 `wsToken`，匹配批次 1 的鉴权实现。
- 统计 `audio_segment` 的首包时间、事件数、`sampleRate` 与解码后字节数。
- WebSocket 未收到 `session_report` 时，轮询 REST `/sessions/{session_id}/report` 兜底确认报告是否已经生成。

## 执行命令

```bash
cd /hy-tmp/ai-product-lab/backend
PYTHONPATH=. python3 scripts/e2e_online_url.py \
  "https://img.naixiai.cn/2026/06/05/ted_Unknown.mp4" \
  150 \
  2>&1 | tee /tmp/e2e_tts_test_full_url.log
```

## 真实链路结果

| 指标 | 结果 |
| --- | --- |
| sessionId | `62323d68-be32-48bc-8408-8270dc8febc6` |
| reportId | `62323d68-be32-48bc-8408-8270dc8febc6-report-bab7502e` |
| 识别 final 句数 | 33 |
| 翻译 final 句数 | 32 |
| 实时纠偏次数 | 3 |
| 首个源文事件 | 1.86s |
| 首个译文事件 | 54.86s |
| 首个音频事件 | 54.86s |
| `audio_segment` 数量 | 414 |
| TTS 采样率 | 24000 Hz |
| 音频总字节 | 5,975,040 bytes |
| 下载报告 | 后端已生成 JSON 报告；REST 兜底可取到 reportId |

前三个音频包均为：

```text
[audio] #1 sampleRate=24000 bytes=15360
[audio] #2 sampleRate=24000 bytes=15360
[audio] #3 sampleRate=24000 bytes=15360
```

样例：

```text
样例原文 : Thank you.
样例译文 : 谢谢。
```

## 字幕质量验证

基于生成报告 `backend/data/reports/62323d68-be32-48bc-8408-8270dc8febc6-report-bab7502e.json`：

| 指标 | 结果 |
| --- | --- |
| 报告时长 | 02:16 |
| 报告 segment 数 | 29 |
| 会后纠偏数 | 24 |
| 最长源文字符数 | 112 |
| 最长实时译文字符数 | 37 |
| 最大单段跨度 | 7465ms |
| 最大相邻起点间隔 | 7465ms |
| CJK 连续重复短语 | 0 |

结论：本轮真实链路没有出现批次二指出的 “xxx走来xxx走来” 式重复；单句长度和跨度均低于批次二验收阈值（源文 <150 字符、译文 <80 字符、相邻起点 <10s）。

## 前端采样率匹配

- 后端真实链路返回 `audio_segment.sampleRate=24000`。
- 前端 `createTtsPlayback` 使用 `new AudioContext({ sampleRate })`，并用同一 `sampleRate` 创建 `AudioBuffer`。
- 因此真实 TTS 24kHz PCM 与前端播放层采样率匹配。

## 遗留问题

1. 在线链接脚本在完整视频最后阶段可能先出现 120s WS 空闲超时；后端仍会完成报告生成。本次已加 REST 报告兜底，避免误报 “会后报告未生成”。
2. 浏览器真实听感仍依赖用户手势解锁 AudioContext、系统音量与浏览器自动播放策略，建议 Demo 前在目标浏览器听测一次。
3. 桌面端 TTS 实际听感未单独测试；本轮只验证 Web 后端事件与前端采样率匹配。

## 结论

批次 4 真实 API 端到端测试通过核心验收：

- 真实 DashScope LiveTranslate 链路可收到 `audio_segment`。
- TTS 输出采样率确认是 24000 Hz。
- 音频格式为 PCM，单包 15360 bytes，累计音频 5,975,040 bytes。
- 字幕长度、时间跨度与重复短语检查通过。
- 会后报告实际生成，REST 兜底可取到 reportId。
