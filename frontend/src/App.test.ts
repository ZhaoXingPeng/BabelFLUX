import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import HomeView from "./views/HomeView.vue";
import WorkbenchView from "./views/WorkbenchView.vue";
import { useSessionStore } from "./stores/session";
import type { SessionReport } from "./api/client";
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
  send: (message: string) => void;
  close: () => void;
}

interface MockAudioSource {
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  connect: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
  buffer: unknown;
}

const mockRuntime = vi.hoisted(() => ({
  createSession: vi.fn(),
  getSessionReport: vi.fn(),
  issueSessionHandoff: vi.fn(),
  reportDownloadUrl: vi.fn(),
  createSessionSocket: vi.fn(),
  routerPush: vi.fn(),
  routerReplace: vi.fn(),
  handlersBySession: new Map<string, SocketHandlers>(),
  sockets: [] as Array<{ sessionId: string; socket: MockSocket }>,
  audioSources: [] as MockAudioSource[],
  audioGain: { gain: { value: 0 }, connect: vi.fn() }
}));

vi.mock("./api/client", () => ({
  createSession: mockRuntime.createSession,
  getSessionReport: mockRuntime.getSessionReport,
  issueSessionHandoff: mockRuntime.issueSessionHandoff,
  reportDownloadUrl: mockRuntime.reportDownloadUrl
}));

vi.mock("./api/ws", () => ({
  createSessionSocket: mockRuntime.createSessionSocket
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: mockRuntime.routerPush, replace: mockRuntime.routerReplace })
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

function buildSocket(
  sessionId: string,
  handlers: SocketHandlers,
  options: { autoStart?: boolean; token?: string } = {}
): MockSocket {
  let socket!: MockSocket;
  const wrappedHandlers: SocketHandlers = {
    ...handlers,
    onOpen: () => {
      handlers.onOpen?.();
      if (options.autoStart ?? true) {
        socket.send(JSON.stringify({ type: "start_session" }));
      }
    }
  };
  socket = {
    readyState: 1,
    sent: [],
    send: vi.fn((message: string) => socket.sent.push(message)),
    close: vi.fn(() => {
      socket.readyState = 3;
      wrappedHandlers.onClose?.();
    })
  };

  mockRuntime.handlersBySession.set(sessionId, wrappedHandlers);
  mockRuntime.sockets.push({ sessionId, socket });
  return socket;
}

function buildStream() {
  const audioTrack = { addEventListener: vi.fn(), removeEventListener: vi.fn(), stop: vi.fn() };
  const videoTrack = { getSettings: () => ({ displaySurface: "browser" }), stop: vi.fn() };
  return {
    getTracks: () => [audioTrack, videoTrack],
    getAudioTracks: () => [audioTrack],
    getVideoTracks: () => [videoTrack]
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

const completedCorrectionReport: SessionReport = {
  reportId: "report-1",
  sessionId: "ui-session-1",
  sessionName: "季度发布会同传",
  domain: "商务",
  sourceLanguage: "en",
  targetLanguage: "zh",
  durationMs: 4300,
  durationText: "00:04",
  generatedAt: "2026-06-07 21:30:00",
  summary: "完整纠偏摘要",
  qualityNotes: "译文整体准确，已统一术语。",
  glossaryHits: [],
  metrics: {
    segments: 1,
    realtimeRevisions: 1,
    finalRevisions: 1,
    durationText: "00:04"
  },
  segments: [
    {
      segmentId: "ui-zh-1",
      startMs: 1200,
      endMs: 4300,
      timecode: "00:01",
      sourceText: "Please review the quarterly launch plan.",
      liveTranslation: "请审阅季度发布计划。",
      finalTranslation: "请审阅季度发布方案。",
      revisedRealtime: true
    }
  ],
  finalRevisions: [
    {
      segmentId: "ui-zh-1",
      beforeText: "请审阅季度发布计划。",
      afterText: "请审阅季度发布方案。",
      reason: "术语统一"
    }
  ],
  realtimeRevisions: [],
  correctionModel: "qwen-plus",
  correctionStatus: "completed",
  correctionError: "",
  correctionElapsedMs: 39_000
};

describe("同传工作台 mock 流程", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", { OPEN: 1 });
    mockRuntime.audioSources = [];
    mockRuntime.audioGain = { gain: { value: 0 }, connect: vi.fn() };
    class MockAudioContext {
      state = "running";
      currentTime = 0;
      destination = {};
      createGain = vi.fn(() => mockRuntime.audioGain);
      createBuffer = vi.fn((_channels: number, length: number, sampleRate: number) => ({
        duration: length / sampleRate,
        getChannelData: () => new Float32Array(length)
      }));
      createBufferSource = vi.fn(() => {
        const source: MockAudioSource = {
          start: vi.fn(),
          stop: vi.fn(),
          connect: vi.fn(),
          addEventListener: vi.fn(),
          buffer: null
        };
        mockRuntime.audioSources.push(source);
        return source;
      });
      resume = vi.fn().mockResolvedValue(undefined);
      close = vi.fn().mockResolvedValue(undefined);
    }
    vi.stubGlobal("AudioContext", MockAudioContext);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue(buildStream()),
        getDisplayMedia: vi.fn().mockResolvedValue(buildStream())
      }
    });
    mockRuntime.createSession.mockReset();
    mockRuntime.getSessionReport.mockReset();
    mockRuntime.issueSessionHandoff.mockReset();
    mockRuntime.reportDownloadUrl.mockReset();
    mockRuntime.createSessionSocket.mockReset();
    mockRuntime.routerPush.mockReset();
    mockRuntime.routerReplace.mockReset();
    mockRuntime.handlersBySession.clear();
    mockRuntime.sockets = [];
    mockRuntime.createSessionSocket.mockImplementation(buildSocket);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((file: File) => `blob:preview-${file.name}`)
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn()
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("默认测试视频字幕滞后音频约 1.5s 逐句产出，并在约 13s 触发上下文纠偏", async () => {
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
    await video.trigger("loadedmetadata");
    expect((video.element as HTMLVideoElement).volume).toBe(0.5);
    expect(mockRuntime.createSession).not.toHaveBeenCalled();
    expect(store.modeStates.quick).toBe("running");
    expect(store.sessionId).toBe("local-test-video-fixture");

    // 视频尚未播放（进度 0）：因产出延迟，右侧不应有任何字幕，也不应回退到示例占位字幕
    expect(store.activeSegmentId).toBeNull();
    expect(wrapper.text()).not.toContain("我感到很幸运");
    expect(wrapper.text()).not.toContain("Today we are going to talk about");

    // 播放到 2s：约 1.5s 延迟后，第一句此时才产出
    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 2 });
    await video.trigger("timeupdate");
    await nextTick();

    expect(store.activeSegmentId).toBe("fixture-seg-001");
    expect(wrapper.text()).toContain("我感到很幸运");
    expect(wrapper.text()).not.toContain("她告诉我");

    // 播放到 14s：第 10 秒那句滞后产出后，在约 13s 完成上下文纠偏（near win 时段不再纠偏）
    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 14 });
    await video.trigger("timeupdate");
    await nextTick();

    expect(store.activeSegmentId).toBe("fixture-seg-004");
    expect(store.revisions).toHaveLength(1);
    expect(wrapper.text()).toContain("有几幅作品没能完全达到她自己的标准");
    expect(wrapper.text()).toContain("已修正");
    expect(wrapper.text()).not.toContain("杰作");

    // 播放到 01:14：字幕滞后约 1.5s，活动段为有效进度(约 72.5s)所在句；同步文案仍按真实进度显示
    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 74 });
    await video.trigger("timeupdate");
    await nextTick();

    expect(store.activeSegmentId).toBe("fixture-seg-025");
    expect(store.sourceSyncState.message).toContain("01:14");
  });

  it("默认测试视频手动暂停后不会被同步状态变化自动拉起播放", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    const video = wrapper.find('[data-testid="fixture-video"]');
    const playSpy = vi.spyOn(video.element as HTMLVideoElement, "play").mockResolvedValue(undefined);

    Object.defineProperty(video.element, "paused", { configurable: true, value: false });
    await video.trigger("pause");
    await nextTick();

    expect(store.modeStates.quick).toBe("paused");
    const playCallsAfterPause = playSpy.mock.calls.length;

    store.sourceSyncState = {
      status: "syncing",
      lagMs: 0,
      message: "本地素材同步 00:12"
    };
    await nextTick();
    await flushPromises();

    expect(playSpy.mock.calls.length).toBe(playCallsAfterPause);
  });

  it.each(["关闭设置", "取消"])("开始前点击%s会返回初始界面", async (buttonLabel) => {
    const wrapper = mountApp();
    const store = useSessionStore();

    expect(wrapper.text()).toContain("同声传译设置");

    await findButton(wrapper, buttonLabel).trigger("click");
    await nextTick();

    expect(wrapper.text()).not.toContain("同声传译设置");
    expect(wrapper.text()).toContain("巴别流 同传");
    expect(store.modeStates.quick).toBe("setup");
    expect(store.activeMode).toBeNull();
    expect(mockRuntime.routerPush).toHaveBeenCalledWith("/");
  });

  it("测试视频自然播放结束后自动出报告，时长为素材完整时长", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    const video = wrapper.find('[data-testid="fixture-video"]');
    await video.trigger("ended");
    await nextTick();

    expect(store.modeStates.quick).toBe("report");
    expect(store.report).not.toBeNull();
    expect(store.report?.durationText).toBe("02:16");
    expect(wrapper.text()).toContain("同传报告");
  });

  it("报告页只提示会后完整纠偏已写入下载报告", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    store.modeStates.quick = "report";
    store.reportLoading = false;
    store.reportError = null;
    store.report = completedCorrectionReport;
    await nextTick();

    expect(wrapper.text()).toContain("全文纠偏已完成");
    expect(wrapper.text()).toContain("完整内容已写入下载报告");
    expect(wrapper.text()).not.toContain("译文整体准确，已统一术语。");
    expect(wrapper.text()).not.toContain("术语统一");
    expect(wrapper.text()).not.toContain("请审阅季度发布方案。");
  });

  it("手动结束时报告时长等于已收听进度，而非 00:00", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    const video = wrapper.find('[data-testid="fixture-video"]');
    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 30 });
    await video.trigger("timeupdate");
    await nextTick();
    expect(store.playbackMs).toBe(30_000);

    const pause = vi.fn();
    Object.defineProperty(video.element, "paused", { configurable: true, value: false });
    Object.defineProperty(video.element, "pause", { configurable: true, value: pause });

    await findButton(wrapper, "结束同传").trigger("click");
    const confirmEndButton = wrapper.findAll("button").find((item) => item.text() === "结束同传");
    expect(confirmEndButton, "confirm end button should exist").toBeTruthy();
    await confirmEndButton!.trigger("click");
    await nextTick();

    expect(store.modeStates.quick).toBe("report");
    expect(store.report?.durationText).toBe("00:30");
    expect(pause).toHaveBeenCalled();

    Object.defineProperty(video.element, "currentTime", { configurable: true, value: 45 });
    await video.trigger("timeupdate");
    expect(store.playbackMs).toBe(30_000);
  });

  it("返回主屏会重置会话，下次进入是全新的待开始任务", async () => {
    const wrapper = mountApp();
    const store = useSessionStore();

    await findButton(wrapper, "开始同传").trigger("click");
    await flushPromises();

    const video = wrapper.find('[data-testid="fixture-video"]');
    await video.trigger("ended");
    await nextTick();
    expect(store.modeStates.quick).toBe("report");

    await findButton(wrapper, "返回主屏").trigger("click");
    await nextTick();

    expect(store.modeStates.quick).toBe("setup");
    expect(store.report).toBeNull();
    expect(store.activeMode).toBeNull();
  });

  it("从快速同传配置走完开始、事件和结束报告", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({
      sessionId: "ui-session-1",
      wsToken: "w_ui",
      status: "created"
    });
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
      sourcePermission: "granted",
      ttsEnabled: false
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

    mockRuntime.handlersBySession.get("ui-session-1")?.onEvent({
      type: "transcript_segment",
      segment: {
        segmentId: "late-after-stop",
        text: "Late transcript should be ignored.",
        language: "en",
        startMs: 5000,
        endMs: 6000,
        status: "final"
      }
    });
    await nextTick();
    expect(wrapper.text()).not.toContain("Late transcript should be ignored.");
  });

  it("启动中重置时旧的创建请求不会连接旧 WebSocket", async () => {
    const quickRequest = deferred<{ sessionId: string; wsToken: string; status: string }>();
    mockRuntime.createSession.mockReturnValueOnce(quickRequest.promise);
    mountApp();
    const store = useSessionStore();
    store.selectQuickSource(store.quickSources.find((source) => source.key === "browser-tab")!);
    store.quickInput.permissionState = "granted";

    const quickStart = store.startMode("quick");
    store.resetMode("quick");

    quickRequest.resolve({ sessionId: "stale-quick", wsToken: "w_stale", status: "created" });
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
    expect(navigator.mediaDevices.getDisplayMedia).toHaveBeenLastCalledWith(
      expect.objectContaining({
        systemAudio: "exclude",
        windowAudio: "exclude"
      })
    );
    expect(store.quickInput.permissionState).toBe("granted");
    expect(store.quickCanStart).toBe(true);

    await setSource(wrapper, "microphone");
    await nextTick();

    expect(store.quickInput.permissionState).toBe("idle");
    expect(store.quickCanStart).toBe(false);
  });

  it("屏幕窗口音频权限会提示共享窗口音频", async () => {
    const wrapper = mountApp();

    await setSource(wrapper, "screen-window");
    await findButton(wrapper, "申请权限").trigger("click");
    await flushPromises();

    expect(navigator.mediaDevices.getDisplayMedia).toHaveBeenLastCalledWith(
      expect.objectContaining({
        systemAudio: "include",
        windowAudio: "window"
      })
    );
  });

  it("upload video source uses media-element PCM streaming and keeps a local preview", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({
      sessionId: "upload-video-session",
      wsToken: "w_upload",
      status: "created"
    });
    const wrapper = mountApp();
    const store = useSessionStore();

    await setSource(wrapper, "video-file");
    const file = new File(["fake mp4"], "demo.mp4", { type: "video/mp4" });
    const input = wrapper.find('input[type="file"]');
    Object.defineProperty(input.element, "files", { configurable: true, value: [file] });
    await input.trigger("change");
    await nextTick();

    expect(store.quickCanStart).toBe(true);
    expect(store.mediaUrl).toBe("blob:preview-demo.mp4");

    await wrapper.find(".settings-footer .primary-button").trigger("click");
    await flushPromises();

    expect(mockRuntime.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        inputMode: "media_element_audio",
        sourceKey: "video-file",
        sourceFileName: "demo.mp4"
      })
    );
    expect(store.mediaUrl).toBe("blob:preview-demo.mp4");
    expect(store.audioUrl).toBeNull();
    const video = wrapper.find('[data-testid="fixture-video"]');
    expect(video.exists()).toBe(true);
    expect(video.attributes("src")).toBe("blob:preview-demo.mp4");

    mockRuntime.handlersBySession.get("upload-video-session")?.onOpen?.();
    await nextTick();

    expect(mockRuntime.createSessionSocket).toHaveBeenCalledWith(
      "upload-video-session",
      expect.any(Object),
      { autoStart: true, token: "w_upload" }
    );

    expect(
      mockRuntime.sockets[0].socket.sent.filter((message) => message === JSON.stringify({ type: "start_session" }))
    ).toHaveLength(1);
    const pauseSpy = vi.spyOn(video.element as HTMLVideoElement, "pause").mockImplementation(() => undefined);
    await video.trigger("play");
    expect(pauseSpy).not.toHaveBeenCalled();
    expect(
      mockRuntime.sockets[0].socket.sent.filter((message) => message === JSON.stringify({ type: "start_session" }))
    ).toHaveLength(1);
    expect(store.sourceSyncState.status).not.toBe("ready");

    Object.defineProperty(video.element, "paused", { configurable: true, value: false });
    await video.trigger("pause");
    await nextTick();

    expect(store.modeStates.quick).toBe("paused");
    expect(mockRuntime.sockets[0].socket.sent).toContain(JSON.stringify({ type: "pause_session" }));
    pauseSpy.mockClear();

    await video.trigger("play");
    await nextTick();

    expect(store.modeStates.quick).toBe("running");
    expect(mockRuntime.sockets[0].socket.sent).toContain(JSON.stringify({ type: "resume_session" }));
    expect(pauseSpy).not.toHaveBeenCalled();

    store.syncPlayback(5);
    mockRuntime.handlersBySession.get("upload-video-session")?.onEvent({
      type: "transcript_segment",
      segment: {
        segmentId: "upload-seg-1",
        text: "The uploaded video is now driving the model input.",
        language: "en",
        startMs: 3000,
        endMs: 7000,
        status: "final"
      }
    });
    await nextTick();

    expect(store.activeSegmentId).toBe("upload-seg-1");
  });

  it("sends ttsEnabled and plays backend audio segments when voice broadcast is enabled", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({
      sessionId: "tts-session",
      wsToken: "w_tts",
      status: "created"
    });
    mountApp();
    const store = useSessionStore();
    store.quickForm.source = "url";
    store.quickInput.url = "https://example.com/demo.mp4";
    store.quickForm.ttsEnabled = true;
    expect(store.ttsVolume).toBe(0.5);

    await store.startMode("quick");
    await flushPromises();

    expect(mockRuntime.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        inputMode: "url",
        sourceUrl: "https://example.com/demo.mp4",
        ttsEnabled: true
      })
    );

    mockRuntime.handlersBySession.get("tts-session")?.onEvent({
      type: "audio_segment",
      segmentId: "seg-tts",
      audioBase64: "AQIDBA==",
      sampleRate: 24000
    });
    await flushPromises();

    expect(mockRuntime.audioSources).toHaveLength(1);
    expect(mockRuntime.audioSources[0].start).toHaveBeenCalled();

    store.setTtsVolume(0.35);
    expect(mockRuntime.audioGain.gain.value).toBe(0.35);

    store.setTtsMuted(true);
    expect(mockRuntime.audioGain.gain.value).toBe(0);
  });

  it("keeps long backend paragraphs in one paired segment card", async () => {
    mountApp();
    const store = useSessionStore();
    store.resetSessionData();
    store.sessionId = "long-backend-session";
    store.activeSegmentId = "seg-long";
    store.sourceSegments = [
      {
        segmentId: "seg-long",
        text:
          "I feel so fortunate that my first job was working at the Museum of Modern Art on a retrospective of painter Elizabeth Murray. I learned so much from her. She told me that a few did not quite meet her own mark for what she wanted them to be.",
        language: "en",
        startMs: 0,
        endMs: 12000,
        status: "final"
      }
    ];
    store.translationSegments = [
      {
        segmentId: "seg-long",
        text:
          "我感到非常幸运，我的第一份工作是在现代艺术博物馆参与画家伊丽莎白默里的回顾展。我从她身上学到了很多。她告诉我，有少数作品并没有完全达到她预期的标准。",
        language: "zh",
        startMs: 0,
        endMs: 12000,
        status: "final"
      }
    ];

    expect(store.transcriptPairs).toHaveLength(1);
    expect(store.transcriptPairs[0].time).toBe("00:00");
    expect(store.transcriptPairs[0].source).toContain("Museum of Modern Art");
    expect(store.transcriptPairs[0].source).toContain("I learned so much");
    expect(store.transcriptPairs[0].translation).toContain("现代艺术博物馆");
    expect(store.transcriptPairs[0].isActive).toBe(true);
  });

  it("does not cross-pair unfinished streaming source and translation chunks", async () => {
    mountApp();
    const store = useSessionStore();
    store.resetSessionData();
    store.sessionId = "partial-backend-session";
    store.activeSegmentId = "seg-partial";
    store.playbackMs = 6000;
    store.sourceSegments = [
      {
        segmentId: "seg-partial",
        text:
          "I feel so fortunate that my first job was working at the Museum of Modern Art. I learned so much from her.",
        language: "en",
        startMs: 0,
        endMs: 0,
        status: "partial"
      }
    ];
    store.translationSegments = [
      {
        segmentId: "seg-partial",
        text: "我感到非常幸运，我的第一份工作是在现代艺术博物馆工作。",
        language: "zh",
        startMs: 0,
        endMs: 0,
        status: "partial"
      }
    ];

    expect(store.transcriptPairs).toHaveLength(1);
    expect(store.transcriptPairs[0].source).toContain("Museum of Modern Art");
    expect(store.transcriptPairs[0].source).toContain("I learned so much");
    expect(store.transcriptPairs[0].translation).not.toContain("等待");
  });

  it("keeps a final translation paired with only the stable part of a partial source", async () => {
    mountApp();
    const store = useSessionStore();
    store.resetSessionData();
    store.sessionId = "partial-source-final-translation";
    store.activeSegmentId = "seg-mixed";
    store.playbackMs = 6000;
    store.sourceSegments = [
      {
        segmentId: "seg-mixed",
        text:
          "I feel so fortunate that my first job was working at the Museum of Modern Art. I learned so much from her.",
        language: "en",
        startMs: 0,
        endMs: 0,
        status: "partial"
      }
    ];
    store.translationSegments = [
      {
        segmentId: "seg-mixed",
        text: "我感到非常幸运，我的第一份工作是在现代艺术博物馆参与画家伊丽莎白默里的回顾展。",
        language: "zh",
        startMs: 0,
        endMs: 6000,
        status: "final"
      }
    ];

    expect(store.transcriptPairs).toHaveLength(1);
    expect(store.transcriptPairs[0].state).toBe("partial");
    expect(store.transcriptPairs[0].source).toContain("I learned so much");
    expect(store.transcriptPairs[0].translation).toContain("现代艺术博物馆");
  });

  it("keeps realtime highlight from jumping back on regressed partial timing", async () => {
    mountApp();
    const store = useSessionStore();
    store.resetSessionData();
    store.sessionId = "realtime-highlight-session";
    store.status = "running";
    store.modeStates.quick = "running";
    store.playbackMs = 12_000;
    store.activeSegmentId = "seg-current";
    store.sourceSegments = [
      {
        segmentId: "seg-first",
        text: "First sentence.",
        language: "en",
        startMs: 0,
        endMs: 4_000,
        status: "final"
      },
      {
        segmentId: "seg-current",
        text: "Current sentence.",
        language: "en",
        startMs: 10_000,
        endMs: 13_000,
        status: "partial"
      }
    ];
    store.translationSegments = [
      {
        segmentId: "seg-first",
        text: "第一句。",
        language: "zh",
        startMs: 0,
        endMs: 4_000,
        status: "final"
      },
      {
        segmentId: "seg-current",
        text: "当前句。",
        language: "zh",
        startMs: 10_000,
        endMs: 13_000,
        status: "partial"
      }
    ];

    store.applyServerEvent({
      type: "transcript_segment",
      segment: {
        segmentId: "seg-current",
        text: "Current sentence is still streaming.",
        language: "en",
        startMs: 0,
        endMs: 0,
        status: "partial"
      }
    });

    expect(store.activeSegmentId).toBe("seg-current");
    expect(store.sourceSegments[1].startMs).toBe(10_000);

    store.applyServerEvent({
      type: "translation_segment",
      segment: {
        segmentId: "seg-wide-old",
        text: "旧的异常长片段。",
        language: "zh",
        startMs: 0,
        endMs: 20_000,
        status: "partial"
      }
    });

    expect(store.activeSegmentId).toBe("seg-current");
  });

  it("does not highlight or show source-only realtime segments as translation results", async () => {
    mountApp();
    const store = useSessionStore();
    store.resetSessionData();
    store.sessionId = "source-only-partial-session";
    store.status = "running";
    store.modeStates.quick = "running";
    store.playbackMs = 34_000;
    store.activeSegmentId = "seg-translated";
    store.sourceSegments = [
      {
        segmentId: "seg-translated",
        text: "I realized that success is a moment, but what we,",
        language: "en",
        startMs: 34_000,
        endMs: 36_000,
        status: "partial"
      }
    ];
    store.translationSegments = [
      {
        segmentId: "seg-translated",
        text: "我意识到，成功只是一瞬间，",
        language: "zh",
        startMs: 34_000,
        endMs: 36_000,
        status: "partial"
      }
    ];

    store.applyServerEvent({
      type: "transcript_segment",
      segment: {
        segmentId: "seg-source-only",
        text: "success",
        language: "en",
        startMs: 34_000,
        endMs: 35_000,
        status: "partial"
      }
    });

    expect(store.activeSegmentId).toBe("seg-translated");
    expect(store.transcriptPairs.some((pair) => pair.segmentId === "seg-source-only")).toBe(false);

    store.applyServerEvent({
      type: "transcript_segment",
      segment: {
        segmentId: "seg-final-source-only",
        text: "I think it comes when we start to value the gift of a near win.",
        language: "en",
        startMs: 45_000,
        endMs: 48_000,
        status: "final"
      }
    });

    expect(store.transcriptPairs.some((pair) => pair.segmentId === "seg-final-source-only")).toBe(false);
    expect(store.transcriptPairs.every((pair) => pair.translation.trim())).toBe(true);
  });

  it("URL 声源需要合法地址后才允许启动，并随 payload 传给后端", async () => {
    mockRuntime.createSession.mockResolvedValueOnce({
      sessionId: "url-session",
      wsToken: "w_url",
      status: "created"
    });
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

  it("主屏激活客户端时直接唤起 standalone 桌面悬浮窗", async () => {
    vi.useFakeTimers();
    const assign = vi.spyOn(window.location, "assign").mockImplementation(() => undefined);

    const wrapper = mountHome();

    await findButton(wrapper, "激活客户端").trigger("click");
    await flushPromises();

    expect(mockRuntime.createSession).not.toHaveBeenCalled();
    expect(mockRuntime.issueSessionHandoff).not.toHaveBeenCalled();
    expect(assign).toHaveBeenCalledWith(
      "lingosync://floating/start?source=system-audio&sourceLanguage=auto&targetLanguage=zh&displayMode=bilingual"
    );
    expect(wrapper.text()).toContain("正在唤起桌面悬浮窗");

    await vi.advanceTimersByTimeAsync(2600);
    await nextTick();

    expect(wrapper.text()).toContain("未检测到桌面客户端");
    await findButton(wrapper, "我已安装，直接打开").trigger("click");
    expect(assign).toHaveBeenCalledTimes(2);
  });

  it("桌面客户端唤起成功后保留提示再自动收起", async () => {
    vi.useFakeTimers();
    vi.spyOn(window.location, "assign").mockImplementation(() => undefined);

    const wrapper = mountHome();
    const store = useSessionStore();

    await findButton(wrapper, "激活客户端").trigger("click");
    await flushPromises();
    window.dispatchEvent(new Event("blur"));
    await nextTick();

    expect(store.desktopLaunchState).toBe("launched");
    expect(wrapper.text()).toContain("桌面悬浮窗已唤起");

    await vi.advanceTimersByTimeAsync(3400);
    await nextTick();
    expect(wrapper.text()).toContain("桌面悬浮窗已唤起");

    await vi.advanceTimersByTimeAsync(100);
    await nextTick();
    expect(store.desktopLaunchState).toBe("idle");
    expect(wrapper.text()).not.toContain("桌面悬浮窗已唤起");
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
