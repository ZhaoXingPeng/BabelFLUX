import { defineStore } from "pinia";
import { createSession } from "../api/client";
import { createSessionSocket } from "../api/ws";
import type {
  RevisionEvent,
  SegmentStatus,
  ServerEvent,
  SessionStatus,
  SourceSyncState,
  SubtitleSegment
} from "../types/events";

let socket: WebSocket | null = null;

const defaultSourceSyncState: SourceSyncState = {
  status: "listening",
  lagMs: 0,
  message: "等待开始会话"
};

interface SessionState {
  sessionId: string | null;
  status: SessionStatus;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  sourceSegments: SubtitleSegment[];
  translationSegments: SubtitleSegment[];
  revisions: RevisionEvent[];
  errorMessage: string | null;
}

function upsertSegment(items: SubtitleSegment[], segment: SubtitleSegment): SubtitleSegment[] {
  const index = items.findIndex((item) => item.segmentId === segment.segmentId);
  if (index === -1) return [...items, segment];
  return items.map((item, itemIndex) => (itemIndex === index ? segment : item));
}

export const useSessionStore = defineStore("session", {
  state: (): SessionState => ({
    sessionId: null,
    status: "idle",
    wsConnected: false,
    sourceSyncState: { ...defaultSourceSyncState },
    sourceSegments: [],
    translationSegments: [],
    revisions: [],
    errorMessage: null
  }),

  getters: {
    activeSourceSegment: (state): SubtitleSegment | undefined =>
      [...state.sourceSegments].reverse().find((segment) => segment.status !== "revised"),
    activeTranslationSegment: (state): SubtitleSegment | undefined =>
      [...state.translationSegments].reverse().find((segment) => segment.status !== "revised")
  },

  actions: {
    async startDemoSession(): Promise<boolean> {
      this.stopSession("idle");
      this.resetSessionData();
      this.status = "connecting";
      this.errorMessage = null;

      try {
        const session = await createSession({
          inputMode: "demo",
          sourceLanguage: "en",
          targetLanguage: "zh"
        });

        this.sessionId = session.sessionId;
        this.connectSocket(session.sessionId);
        return true;
      } catch (error) {
        this.status = "error";
        this.errorMessage =
          error instanceof Error ? error.message : "创建会话失败，请确认后端已启动";
        return false;
      }
    },

    stopSession(nextStatus: SessionStatus = "stopped") {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop_session" }));
      }
      socket?.close();
      socket = null;
      this.wsConnected = false;
      this.status = nextStatus;
    },

    pauseSession() {
      if (this.status === "running") this.status = "paused";
    },

    resumeSession() {
      if (this.status === "paused") this.status = "running";
    },

    resetSessionData() {
      this.sessionId = null;
      this.sourceSyncState = { ...defaultSourceSyncState };
      this.sourceSegments = [];
      this.translationSegments = [];
      this.revisions = [];
      this.errorMessage = null;
    },

    connectSocket(sessionId: string) {
      socket?.close();
      socket = createSessionSocket(sessionId, {
        onOpen: () => {
          this.wsConnected = true;
          this.status = "running";
        },
        onClose: () => {
          this.wsConnected = false;
          if (this.status === "running") this.status = "stopped";
        },
        onError: (message) => {
          this.status = "error";
          this.errorMessage = message;
        },
        onEvent: (event) => this.applyServerEvent(event)
      });
    },

    applyServerEvent(event: ServerEvent) {
      if (event.type === "session_started") {
        this.sessionId = event.sessionId;
        return;
      }

      if (event.type === "source_sync_state") {
        this.sourceSyncState = event.state;
        return;
      }

      if (event.type === "transcript_segment") {
        this.sourceSegments = upsertSegment(this.sourceSegments, event.segment);
        return;
      }

      if (event.type === "translation_segment") {
        this.translationSegments = upsertSegment(this.translationSegments, event.segment);
        return;
      }

      if (event.type === "revision_event") {
        this.revisions = [event.revision, ...this.revisions].slice(0, 20);
        this.markRevised(event.revision.targetSegmentIds);
        return;
      }

      if (event.type === "error") {
        this.status = "error";
        this.errorMessage = event.message;
      }
    },

    markRevised(segmentIds: string[]) {
      const updateStatus = (segment: SubtitleSegment): SubtitleSegment =>
        segmentIds.includes(segment.segmentId)
          ? { ...segment, status: "revised" as SegmentStatus }
          : segment;

      this.sourceSegments = this.sourceSegments.map(updateStatus);
      this.translationSegments = this.translationSegments.map(updateStatus);
    }
  }
});
