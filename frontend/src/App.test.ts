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

function buildStream() {
  return {
    getTracks: () => [{ stop: vi.fn() }]
  };
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
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue(buildStream()),
        getDisplayMedia: vi.fn().mockResolvedValue(buildStream())
      }
    });
    mockRuntime.createSession.mockReset();
    mockRuntime.createSessionSocket.mockReset();
    mockRuntime.handlersBySession.clear();
    mockRuntime.sockets = [];
    mockRuntime.createSessionSocket.mockImplementation(buildSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("默认加载测试视频、提取音频和字幕，并按播放时间触发本地纠错", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    const video = wrapper.find('[data-testid="fixture-video"]');
    const audio = wrapper.find('[data-testid="fixture-audio"]');
    expect(video.attributes("src")).toBe("/fixtures/test-video/video.mp4");
    expect(audio.attributes("src")).toBe("/fixtures/test-video/voice.m4a");
    expect(wrapper.text()).toContain("video.mp4 / voice.m4a / en.txt / ch.txt 已就绪");
    expect(wrapper.text()).toContain("我感到很幸运");

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    expect(mockRuntime.createSession).not.toHaveBeenCalled();
    expect(store.modeStates.quick).toBe("running");
    expect(store.sessionId).toBe("local-test-video-fixture");

    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 53 });
    await video.trigger("timeupdate");
    await nextTick();

    expect(store.activeSegmentId).toBe("fixture-seg-016");
    expect(wrapper.text()).toContain("我想，当我们开始珍视一次差一点成功的馈赠时，转变就发生了，");
    expect(wrapper.text()).toContain("已修正");
    expect(wrapper.text()).toContain("near win");

    Object.defineProperty(audio.element, "currentTime", { configurable: true, value: 74 });
    await audio.trigger("timeupdate");
    await nextTick();

    expect(store.activeSegmentId).toBe("fixture-seg-026");
    expect(store.sourceSyncState.message).toContain("01:14");
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
    await findButton(wrapper, "申请权限").trigger("click");
    await flushPromises();
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
      sourceKey: "browser-tab",
      sourceFileName: undefined,
      sourceUrl: undefined,
      sourcePermission: "granted"
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

    expect(wrapper.text()).toContain("已连接");
    expect(wrapper.text()).not.toContain("快速同传设置");
    expect(wrapper.text()).toContain("请审阅季度发布计划。");
    expect(wrapper.text()).toContain("revised");

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

  it("启动中重置时旧的创建请求不会连接旧 WebSocket", async () => {
    const quickRequest = deferred<{ sessionId: string; status: string }>();
    mockRuntime.createSession.mockReturnValueOnce(quickRequest.promise);
    mountApp();
    const store = useSessionStore();
    store.selectQuickSource(store.quickSources.find((source) => source.key === "browser-tab")!);
    store.quickInput.permissionState = "granted";

    const quickStart = store.startMode("quick");
    store.resetMode("quick");

    quickRequest.resolve({ sessionId: "stale-quick", status: "created" });
    await quickStart;

    expect(mockRuntime.handlersBySession.has("stale-quick")).toBe(false);
    expect(store.activeMode).toBe(null);
    expect(store.modeStates.quick).toBe("setup");
    expect(mockRuntime.createSessionSocket).not.toHaveBeenCalled();
  });

  it("切换权限类声源会重置已有授权状态", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "浏览器标签页音频").trigger("click");
    await findButton(wrapper, "申请权限").trigger("click");
    await flushPromises();
    expect(store.quickInput.permissionState).toBe("granted");
    expect(store.quickCanStart).toBe(true);

    await findButton(wrapper, "麦克风").trigger("click");
    await nextTick();

    expect(store.quickInput.permissionState).toBe("idle");
    expect(store.quickCanStart).toBe(false);
  });

  it("URL 声源需要合法地址后才允许启动，并随 payload 传给后端", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({ sessionId: "url-session", status: "created" });
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "URL").trigger("click");
    await nextTick();
    const startButton = findButton(wrapper, "开始同传");
    expect((startButton.element as HTMLButtonElement).disabled).toBe(true);

    await wrapper.find('input[type="url"]').setValue("not-a-url");
    expect(wrapper.text()).toContain("URL 格式不正确");
    expect((startButton.element as HTMLButtonElement).disabled).toBe(true);

    await wrapper.find('input[type="url"]').setValue("https://example.com/live");
    await nextTick();
    expect(store.quickCanStart).toBe(true);

    await startButton.trigger("click");
    await flushPromises();

    expect(mockRuntime.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        inputMode: "url",
        sourceKey: "url",
        sourceUrl: "https://example.com/live",
        sourcePermission: "idle"
      })
    );
  });
});
