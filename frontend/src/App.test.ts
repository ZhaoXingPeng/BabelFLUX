import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import App from "./App.vue";
import { useSessionStore } from "./stores/session";
import type { ServerEvent } from "./types/events";

interface SocketHandlers {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (message: string) => void;
  onEvent: (event: ServerEvent) => void;
}

interface MockSocket {
  readyState: number;
  sent: string[];
  send: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
}

const mockRuntime = vi.hoisted(() => ({
  createSession: vi.fn(),
  createSessionSocket: vi.fn(),
  handlersBySession: new Map<string, SocketHandlers>(),
  sockets: [] as Array<{ sessionId: string; socket: MockSocket }>
}));

vi.mock("./api/client", () => ({
  createSession: mockRuntime.createSession
}));

vi.mock("./api/ws", () => ({
  createSessionSocket: mockRuntime.createSessionSocket
}));

function mountApp(): VueWrapper {
  const pinia = createPinia();
  setActivePinia(pinia);
  return mount(App, {
    global: {
      plugins: [pinia]
    }
  });
}

function findButton(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll("button").find((item) => item.text().includes(text));
  expect(button, `button "${text}" should exist`).toBeTruthy();
  return button!;
}

function buildSocket(sessionId: string, handlers: SocketHandlers): MockSocket {
  const socket: MockSocket = {
    readyState: 1,
    sent: [],
    send: vi.fn((message: string) => socket.sent.push(message)),
    close: vi.fn(() => {
      socket.readyState = 3;
      handlers.onClose?.();
    })
  };

  mockRuntime.handlersBySession.set(sessionId, handlers);
  mockRuntime.sockets.push({ sessionId, socket });
  return socket;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

const transcriptEvent: ServerEvent = {
  type: "transcript_segment",
  segment: {
    segmentId: "ui-src-1",
    text: "Please review the quarterly launch plan.",
    language: "en",
    startMs: 1200,
    endMs: 4300,
    status: "final"
  }
};

const translationEvent: ServerEvent = {
  type: "translation_segment",
  segment: {
    segmentId: "ui-zh-1",
    text: "请审阅季度发布计划。",
    language: "zh",
    startMs: 1200,
    endMs: 4300,
    status: "final"
  }
};

const revisionEvent: ServerEvent = {
  type: "revision_event",
  revision: {
    revisionId: "ui-rev-1",
    targetSegmentIds: ["ui-zh-1"],
    beforeText: "季度发布计划",
    afterText: "季度发布方案",
    reason: "术语修正",
    confidence: 0.93
  }
};

describe("App 同传 mock 流程", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", { OPEN: 1 });
    mockRuntime.createSession.mockReset();
    mockRuntime.createSessionSocket.mockReset();
    mockRuntime.handlersBySession.clear();
    mockRuntime.sockets = [];
    mockRuntime.createSessionSocket.mockImplementation(buildSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("从快速同传配置走完开始、事件、暂停、继续和结束报告", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({ sessionId: "ui-session-1", status: "created" });
    const wrapper = mountApp();
    const store = useSessionStore();

    await wrapper.find('input[type="text"]').setValue("季度发布会同传");
    const selects = wrapper.findAll("select");
    await selects[0].setValue("商务");
    await selects[1].setValue("英语");
    await selects[2].setValue("日语");
    await selects[3].setValue("高准确");
    await findButton(wrapper, "浏览器标签页音频").trigger("click");
    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    expect(mockRuntime.createSession).toHaveBeenCalledWith({
      inputMode: "browser_audio",
      sourceLanguage: "en",
      targetLanguage: "ja",
      productMode: "quick",
      sessionName: "季度发布会同传",
      domain: "商务",
      modelProfile: "高准确",
      sourceKey: "browser-tab"
    });
    expect(store.modeStates.quick).toBe("running");

    mockRuntime.handlersBySession.get("ui-session-1")?.onOpen?.();
    mockRuntime.handlersBySession.get("ui-session-1")?.onEvent({
      type: "source_sync_state",
      state: { status: "syncing", lagMs: 120, message: "同步正常" }
    });
    mockRuntime.handlersBySession.get("ui-session-1")?.onEvent(transcriptEvent);
    mockRuntime.handlersBySession.get("ui-session-1")?.onEvent(translationEvent);
    mockRuntime.handlersBySession.get("ui-session-1")?.onEvent(revisionEvent);
    await nextTick();

    expect(wrapper.text()).toContain("WebSocket 已连接");
    expect(wrapper.text()).toContain("请审阅季度发布计划。");
    expect(wrapper.text()).toContain("季度发布计划 -> 季度发布方案");

    await findButton(wrapper, "暂停").trigger("click");
    expect(store.status).toBe("paused");
    expect(mockRuntime.sockets[0].socket.sent).toContain(JSON.stringify({ type: "pause_session" }));

    await findButton(wrapper, "继续").trigger("click");
    expect(store.status).toBe("running");
    expect(mockRuntime.sockets[0].socket.sent).toContain(JSON.stringify({ type: "resume_session" }));

    await findButton(wrapper, "结束").trigger("click");
    expect(wrapper.text()).toContain("结束本次同传？");
    await findButton(wrapper, "结束会议").trigger("click");
    await nextTick();

    expect(store.modeStates.quick).toBe("report");
    expect(wrapper.text()).toContain("会议报告");
    expect(wrapper.text()).toContain("1 条");
  });

  it("快速切换模式时旧的创建请求不会连接旧 WebSocket", async () => {
    const quickRequest = deferred<{ sessionId: string; status: string }>();
    const floatingRequest = deferred<{ sessionId: string; status: string }>();
    mockRuntime.createSession
      .mockReturnValueOnce(quickRequest.promise)
      .mockReturnValueOnce(floatingRequest.promise);
    mountApp();
    const store = useSessionStore();

    const quickStart = store.startMode("quick");
    const floatingStart = store.startMode("floating");

    quickRequest.resolve({ sessionId: "stale-quick", status: "created" });
    await quickStart;
    expect(mockRuntime.handlersBySession.has("stale-quick")).toBe(false);
    expect(store.activeMode).toBe("floating");
    expect(store.modeStates.quick).toBe("setup");

    floatingRequest.resolve({ sessionId: "current-floating", status: "created" });
    await floatingStart;

    expect(mockRuntime.handlersBySession.has("current-floating")).toBe(true);
    expect(store.sessionId).toBe("current-floating");
    expect(store.modeStates.floating).toBe("running");
    expect(mockRuntime.createSessionSocket).toHaveBeenCalledTimes(1);
  });
});
