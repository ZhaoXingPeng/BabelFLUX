export interface TimedSubtitleLine {
  startMs: number;
  text: string;
}

export interface BilingualSubtitleSegment {
  segmentId: string;
  startMs: number;
  endMs: number;
  source: string;
  target: string;
  sourceLanguage: string;
  targetLanguage: string;
}

const TIMED_LINE_PATTERN = /^(\d{2}(?::\d{2}){1,2})\s+(.+)$/;

export function parseTimestamp(timestamp: string): number {
  const parts = timestamp.split(":").map((part) => Number(part));
  if (parts.some((part) => Number.isNaN(part))) throw new Error(`Invalid timestamp: ${timestamp}`);

  if (parts.length === 2) {
    const [minutes, seconds] = parts;
    return (minutes * 60 + seconds) * 1000;
  }

  if (parts.length === 3) {
    const [hours, minutes, seconds] = parts;
    return (hours * 3600 + minutes * 60 + seconds) * 1000;
  }

  throw new Error(`Invalid timestamp: ${timestamp}`);
}

export function parseTimedSubtitleText(text: string): TimedSubtitleLine[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => TIMED_LINE_PATTERN.test(line))
    .map((line) => {
      const match = line.match(TIMED_LINE_PATTERN);
      if (!match) throw new Error(`Invalid subtitle line: ${line}`);

      return {
        startMs: parseTimestamp(match[1]),
        text: match[2].trim()
      };
    });
}

export function buildBilingualTimeline(
  sourceText: string,
  targetText: string,
  durationMs: number,
  sourceLanguage = "zh",
  targetLanguage = "en"
): BilingualSubtitleSegment[] {
  const sourceLines = parseTimedSubtitleText(sourceText);
  const targetLines = parseTimedSubtitleText(targetText);
  const count = Math.min(sourceLines.length, targetLines.length);

  return Array.from({ length: count }, (_, index) => {
    const source = sourceLines[index];
    const target = targetLines[index];
    const nextSource = sourceLines[index + 1];
    const endMs = nextSource?.startMs ?? durationMs;

    return {
      segmentId: `fixture-seg-${String(index + 1).padStart(3, "0")}`,
      startMs: source.startMs,
      endMs,
      source: source.text,
      target: target.text,
      sourceLanguage,
      targetLanguage
    };
  });
}

export function findActiveSegment(
  segments: BilingualSubtitleSegment[],
  playbackMs: number
): BilingualSubtitleSegment | null {
  return (
    segments.find((segment) => playbackMs >= segment.startMs && playbackMs < segment.endMs) ??
    segments.find((segment) => playbackMs === segment.endMs) ??
    null
  );
}
