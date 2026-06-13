export interface TimedSubtitleLine {
  startMs: number;
  text: string;
}

export interface BilingualSubtitleSegment {
  segmentId: string;
  startMs: number;
  endMs: number;
  en: string;
  zh: string;
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
  englishText: string,
  chineseText: string,
  durationMs: number
): BilingualSubtitleSegment[] {
  const englishLines = parseTimedSubtitleText(englishText);
  const chineseLines = parseTimedSubtitleText(chineseText);
  const count = Math.min(englishLines.length, chineseLines.length);

  return Array.from({ length: count }, (_, index) => {
    const english = englishLines[index];
    const chinese = chineseLines[index];
    const nextEnglish = englishLines[index + 1];
    const endMs = nextEnglish?.startMs ?? durationMs;

    return {
      segmentId: `fixture-seg-${String(index + 1).padStart(3, "0")}`,
      startMs: english.startMs,
      endMs,
      en: english.text,
      zh: chinese.text
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
