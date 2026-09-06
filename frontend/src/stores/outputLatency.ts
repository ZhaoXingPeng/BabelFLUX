export interface OutputLatencyTrackerOptions {
  fallbackMs: number;
  minMs: number;
  maxMs: number;
  sampleSize: number;
}

export interface OutputLatencyTracker {
  readonly estimateMs: number;
  record(segmentId: string, startMs: number, playbackMs: number): void;
  reset(): void;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

/** Tracks a bounded, de-duplicated latency sample without I/O or UI state. */
export function createOutputLatencyTracker(
  options: OutputLatencyTrackerOptions
): OutputLatencyTracker {
  let estimateMs = options.fallbackMs;
  const samples: number[] = [];
  const sampledSegmentIds = new Set<string>();

  return {
    get estimateMs() {
      return estimateMs;
    },

    record(segmentId, startMs, playbackMs) {
      if (sampledSegmentIds.has(segmentId)) return;
      if (playbackMs <= 0 || startMs < 0) return;
      const latency = playbackMs - startMs;
      if (latency < options.minMs || latency > options.maxMs) return;

      sampledSegmentIds.add(segmentId);
      samples.push(latency);
      while (samples.length > options.sampleSize) samples.shift();
      estimateMs = median(samples) || options.fallbackMs;
    },

    reset() {
      estimateMs = options.fallbackMs;
      samples.length = 0;
      sampledSegmentIds.clear();
    }
  };
}
