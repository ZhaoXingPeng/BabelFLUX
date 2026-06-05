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
    sourceSyncState: {
      status: "listening",
      lagMs: 0,
      message: "等待开始会话"
    },
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
    async startDemoSession() {
      this.status = "connecting";
      this.errorMessage = null;

      const session = await createSession({
        inputMode: "demo",
        sourceLanguage: "en",
        targetLanguage: "zh"
      });

      this.sessionId = session.sessionId;
      this.connectSocket(session.sessionId);
    },

    stopSession() {
      socket?.close();
      socket = null;
      this.wsConnected = false;
      this.status = "stopped";
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
