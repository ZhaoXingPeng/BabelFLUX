"""在线链接端到端联调（真实链路）。

用法：
    PYTHONPATH=. python3 scripts/e2e_online_url.py <媒体直链> [时长上限秒]

流程：创建 url 模式会话 → WS start_session → 收集 transcript/translation/
revision 事件，达到时长上限或自然结束后 stop_session → 等待 session_report，
打印识别/翻译/实时纠偏/报告指标。用于验证「在线链接」全链路。
"""
import asyncio
import json
import os
import sys
import time

import httpx
import websockets

API = os.getenv("BABELFLUX_E2E_API", "http://127.0.0.1:8000/api")
WS = os.getenv("BABELFLUX_E2E_WS", "ws://127.0.0.1:8000/api")


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://img.naixiai.cn/2026/06/05/ted_Unknown.mp4"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            f"{API}/sessions",
            json={
                "inputMode": "url",
                "sourceLanguage": "en",
                "targetLanguage": "zh",
                "productMode": "quick",
                "sessionName": "在线链接E2E",
                "domain": "通用",
                "modelProfile": "快速低延迟",
                "sourceKey": "url",
                "sourceUrl": url,
            },
        )
        resp.raise_for_status()
        session_id = resp.json()["sessionId"]
    print(f"[session] {session_id}\n[url] {url}\n[budget] {budget}s")

    src_final = tr_final = revisions = 0
    report_id = None
    first_src_at = None
    first_src_event_at = None
    first_tr_event_at = None
    started = time.monotonic()
    sample_src = sample_tr = None

    async with websockets.connect(f"{WS}/ws/sessions/{session_id}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "start_session"}))
        stopped = False
        while True:
            try:
                # 放宽：本链路分段较粗（整段才 final），且 stop 后 finalize 要调
                # qwen-plus 处理整稿，需较长等待才能收到 session_report。
                raw = await asyncio.wait_for(ws.recv(), timeout=70)
            except TimeoutError:
                print("[warn] 70s 无事件，结束")
                break
            evt = json.loads(raw)
            t = evt.get("type")
            if t == "transcript_segment":
                if first_src_event_at is None:
                    first_src_event_at = time.monotonic() - started
                if evt["segment"]["status"] in ("final", "revised"):
                    src_final += 1
                    if first_src_at is None:
                        first_src_at = time.monotonic() - started
                    sample_src = evt["segment"]["text"]
            elif t == "translation_segment":
                if first_tr_event_at is None:
                    first_tr_event_at = time.monotonic() - started
                if evt["segment"]["status"] in ("final", "revised"):
                    tr_final += 1
                    sample_tr = evt["segment"]["text"]
            elif t == "revision_event":
                revisions += 1
                before = evt["revision"]["beforeText"]
                after = evt["revision"]["afterText"]
                print(f"[revision] {before} -> {after}")
            elif t == "session_report":
                report_id = evt.get("reportId")
                break
            elif t == "error":
                print(f"[error] {evt.get('message')}")

            if not stopped and time.monotonic() - started > budget:
                stopped = True
                print(f"[budget] 达到 {budget}s，发送 stop_session")
                await ws.send(json.dumps({"type": "stop_session"}))

    print("\n=== 在线链接 E2E 结果 ===")
    print(f"识别 final 句数 : {src_final}")
    print(f"翻译 final 句数 : {tr_final}")
    print(f"实时纠偏次数    : {revisions}")
    print(
        f"首个源文事件    : {first_src_event_at:.2f}s"
        if first_src_event_at
        else "首个源文事件    : N/A"
    )
    print(
        f"首个译文事件    : {first_tr_event_at:.2f}s"
        if first_tr_event_at
        else "首个译文事件    : N/A"
    )
    print(f"首句识别延迟    : {first_src_at:.2f}s" if first_src_at else "首句识别延迟    : N/A")
    print(f"会后报告        : {'已生成 ' + report_id if report_id else '未生成'}")
    if sample_src:
        print(f"样例原文        : {sample_src[:80]}")
    if sample_tr:
        print(f"样例译文        : {sample_tr[:80]}")

    if report_id:
        async with httpx.AsyncClient(timeout=30) as http:
            for fmt in ("txt", "srt", "md", "json"):
                r = await http.get(
                    f"{API}/sessions/{session_id}/report/download",
                    params={"format": fmt},
                )
                print(f"下载[{fmt}] {r.status_code} {len(r.content)}B")


if __name__ == "__main__":
    asyncio.run(main())
