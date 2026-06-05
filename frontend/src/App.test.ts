import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import HomeView from "./views/HomeView.vue";
import WorkbenchView from "./views/WorkbenchView.vue";
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
  issueSessionHandoff: vi.fn(),
  createSessionSocket: vi.fn(),
  handlersBySession: new Map<string, SocketHandlers>(),
  sockets: [] as Array<{ sessionId: string; socket: MockSocket }>
}));

vi.mock("./api/client", () => ({
  createSession: mockRuntime.createSession,
  issueSessionHandoff: mockRuntime.issueSessionHandoff
}));

vi.mock("./api/ws", () => ({
  createSessionSocket: mockRuntime.createSessionSocket
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() })
}));

function mountApp(): VueWrapper {
  const pinia = createPinia();
  setActivePinia(pinia);
  return mount(WorkbenchView, {
    global: {
      plugins: [pinia]
    }
  });
}

function mountHome(): VueWrapper {
  const pinia = createPinia();
  setActivePinia(pinia);
  return mount(HomeView, {
    global: {
      plugins: [pinia]
    }
  });
}

function findButton(wrapper: VueWrapper, text: string) {
  const button = wrapper
    .findAll("button")
    .find(
      (item) =>
        item.text().includes(text) ||
        item.attributes("aria-label")?.includes(text) ||
        item.attributes("title")?.includes(text)
    );
  expect(button, `button "${text}" should exist`).toBeTruthy();
  return button!;
}

async function chooseSelect(wrapper: VueWrapper, name: string, value: string) {
  const root = wrapper.find(`[data-select-id="${name}"]`);
  expect(root.exists(), `select "${name}" should exist`).toBe(true);

  const trigger = root.find(".select-trigger");
  expect(trigger.exists(), `select "${name}" trigger should exist`).toBe(true);
  await trigger.trigger("keydown", { key: "ArrowDown" });
  await nextTick();

  const option = root.find(`[data-select-option="${value}"]`);
  expect(option.exists(), `select "${name}" option "${value}" should exist`).toBe(true);
  await option.trigger("click");
  await nextTick();
}

async function setSource(wrapper: VueWrapper, sourceKey: string) {
  await chooseSelect(wrapper, "source-select", sourceKey);
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

describe("同传工作台 mock 流程", () => {
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
    mockRuntime.issueSessionHandoff.mockReset();
    mockRuntime.createSessionSocket.mockReset();
    mockRuntime.handlersBySession.clear();
    mockRuntime.sockets = [];
    mockRuntime.createSessionSocket.mockImplementation(buildSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("默认加载测试视频、提取音频和字幕，并按播放时间触发本地纠错", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    expect(wrapper.find('[data-testid="fixture-video"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="fixture-audio"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("同声传译设置");
    expect(wrapper.text()).toContain("video.mp4 / voice.m4a / en.txt / ch.txt 已就绪");

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    const video = wrapper.find('[data-testid="fixture-video"]');
    const audio = wrapper.find('[data-testid="fixture-audio"]');
    expect(video.attributes("src")).toBe("/fixtures/test-video/video.mp4");
    expect(audio.exists()).toBe(false);
    expect(wrapper.text()).toContain("我感到很幸运");

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

    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 74 });
    await video.trigger("timeupdate");
    await nextTick();

    expect(store.activeSegmentId).toBe("fixture-seg-026");
    expect(store.sourceSyncState.message).toContain("01:14");
  });

  it("从快速同传配置走完开始、事件和结束报告", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({ sessionId: "ui-session-1", status: "created" });
    const wrapper = mountApp();
    const store = useSessionStore();

    await wrapper.find('input[type="text"]').setValue("季度发布会同传");
    await chooseSelect(wrapper, "domain", "商务");
    await chooseSelect(wrapper, "source-language", "英语");
    await chooseSelect(wrapper, "target-language", "日语");
    await setSource(wrapper, "browser-tab");
    await chooseSelect(wrapper, "model-profile", "高准确");
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
    expect(wrapper.text()).not.toContain("同声传译设置");
    expect(wrapper.text()).toContain("季度发布方案");
    expect(wrapper.text()).toContain("原译季度发布计划");
    expect(wrapper.text()).toContain("已修正");

    await findButton(wrapper, "结束同传").trigger("click");
    expect(wrapper.text()).toContain("结束本次同传？");
    const confirmEndButton = wrapper.findAll("button").find((item) => item.text() === "结束同传");
    expect(confirmEndButton, "confirm end button should exist").toBeTruthy();
    await confirmEndButton!.trigger("click");
    await nextTick();

    expect(store.modeStates.quick).toBe("report");
    expect(wrapper.text()).toContain("同传报告");
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

    await setSource(wrapper, "browser-tab");
    await findButton(wrapper, "申请权限").trigger("click");
    await flushPromises();
    expect(store.quickInput.permissionState).toBe("granted");
    expect(store.quickCanStart).toBe(true);

    await setSource(wrapper, "microphone");
    await nextTick();

    expect(store.quickInput.permissionState).toBe("idle");
    expect(store.quickCanStart).toBe(false);
  });

  it("URL 声源需要合法地址后才允许启动，并随 payload 传给后端", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({ sessionId: "url-session", status: "created" });
    const wrapper = mountApp();
    const store = useSessionStore();

    await setSource(wrapper, "url");
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

  it("主屏激活客户端时创建桌面会话并签发 handoff token", async () => {
    vi.useFakeTimers();
    const assign = vi.spyOn(window.location, "assign").mockImplementation(() => undefined);
    mockRuntime.createSession.mockResolvedValueOnce({ sessionId: "desktop-home-session", status: "created" });
    mockRuntime.issueSessionHandoff.mockResolvedValueOnce({
      handoffToken: "h_home",
      expiresAt: "2026-06-06T00:00:30Z",
      deepLinkUrl:
        "lingosync://floating/start?sessionId=desktop-home-session&displayMode=bilingual&token=h_home"
    });

    const wrapper = mountHome();

    await findButton(wrapper, "激活客户端").trigger("click");
    await flushPromises();

    expect(mockRuntime.createSession).toHaveBeenCalledWith({
      inputMode: "system_audio",
      sourceLanguage: "auto",
      targetLanguage: "zh",
      productMode: "floating",
      sessionName: "客户端悬浮字幕",
      domain: "通用",
      modelProfile: "快速低延迟",
      sourceKey: "system-audio",
      sourceFileName: undefined,
      sourceUrl: undefined,
      sourcePermission: "idle"
    });
    expect(mockRuntime.issueSessionHandoff).toHaveBeenCalledWith(
      "desktop-home-session",
      expect.objectContaining({
        source: "system-audio",
        sourceLanguage: "auto",
        targetLanguage: "zh",
        displayMode: "bilingual"
      })
    );
    expect(assign).toHaveBeenCalledWith(
      "lingosync://floating/start?sessionId=desktop-home-session&displayMode=bilingual&token=h_home"
    );
    expect(wrapper.text()).toContain("正在唤起桌面悬浮窗");

    await vi.advanceTimersByTimeAsync(2600);
    await nextTick();

    expect(wrapper.text()).toContain("未检测到桌面客户端");
    await findButton(wrapper, "我已安装，直接打开").trigger("click");
    expect(assign).toHaveBeenCalledTimes(2);
  });

  it("投送桌面悬浮窗时签发 handoff token，并在未唤起时提供网页悬浮回退", async () => {
    vi.useFakeTimers();
    const assign = vi.spyOn(window.location, "assign").mockImplementation(() => undefined);
    mockRuntime.issueSessionHandoff.mockResolvedValueOnce({
      handoffToken: "h_demo",
      expiresAt: "2026-06-06T00:00:30Z",
      deepLinkUrl: "lingosync://floating/start?sessionId=local-test-video-fixture&displayMode=bilingual&token=h_demo"
    });

    const wrapper = mountApp();
    const store = useSessionStore();
    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    await findButton(wrapper, "投送桌面").trigger("click");
    await flushPromises();

    expect(mockRuntime.issueSessionHandoff).toHaveBeenCalledWith(
      "local-test-video-fixture",
      expect.objectContaining({
        source: "fixture-video",
        sourceLanguage: "en",
        targetLanguage: "zh",
        displayMode: "bilingual"
      })
    );
    expect(assign).toHaveBeenCalledWith(
      "lingosync://floating/start?sessionId=local-test-video-fixture&displayMode=bilingual&token=h_demo"
    );
    expect(store.desktopLaunchState).toBe("launching");

    await vi.advanceTimersByTimeAsync(2600);
    await nextTick();

    expect(store.desktopLaunchState).toBe("fallback");
    expect(wrapper.text()).toContain("未检测到桌面客户端");

    await findButton(wrapper, "我已安装，直接打开").trigger("click");
    expect(assign).toHaveBeenCalledTimes(2);
    expect(store.desktopLaunchState).toBe("launching");

    await vi.advanceTimersByTimeAsync(2600);
    await nextTick();
    expect(store.desktopLaunchState).toBe("fallback");

    await findButton(wrapper, "继续网页悬浮").trigger("click");
    await nextTick();

    expect(store.selectedDisplayMode).toBe("悬浮字幕");
    expect(store.desktopDownloadPromptOpen).toBe(false);
  });
});
