<script setup lang="ts">
type IconName =
  | "arrow-left"
  | "blinds"
  | "check"
  | "chevron-down"
  | "clock-3"
  | "refresh-cw"
  | "languages"
  | "monitor-up"
  | "picture-in-picture-2"
  | "pin"
  | "pin-off"
  | "plus"
  | "sliders-horizontal"
  | "square"
  | "type"
  | "trash-2"
  | "upload"
  | "volume-2"
  | "volume-x"
  | "x";

const props = withDefaults(
  defineProps<{
    name: IconName;
    size?: number;
    strokeWidth?: number;
  }>(),
  {
    size: 18,
    strokeWidth: 2
  }
);

const ICON_PATHS: Record<IconName, string[]> = {
  "arrow-left": ["m12 19-7-7 7-7", "M19 12H5"],
  blinds: [
    "M3 3h18",
    "M20 7H8",
    "M20 11H8",
    "M20 15H8",
    "M10 19h10",
    "M4 3v14",
    "M4 17a2 2 0 0 0 2 2h2"
  ],
  check: ["M20 6 9 17l-5-5"],
  "chevron-down": ["m6 9 6 6 6-6"],
  "clock-3": ["M12 6v6h4", "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"],
  "refresh-cw": ["M3 12a9 9 0 0 1 15-6.7L21 8", "M21 3v5h-5", "M21 12a9 9 0 0 1-15 6.7L3 16", "M3 21v-5h5"],
  languages: ["m5 8 6 6", "m4 14 6-6 2-3", "M2 5h12", "M7 2h1", "m22 22-5-10-5 10", "M14 18h6"],
  "monitor-up": [
    "M8 21h8",
    "M12 17v4",
    "M4 17h16a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2Z",
    "M12 13V7",
    "m8 5-8-8-8 8"
  ],
  "picture-in-picture-2": [
    "M21 9V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3",
    "M11 13h8a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-8z"
  ],
  pin: [
    "M12 17v5",
    "M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16h14v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1z"
  ],
  "pin-off": [
    "M12 17v5",
    "M15 7h1a2 2 0 0 0 0-4H8",
    "M9 7h.01",
    "M15 10.76c0 .35.09.69.26 1",
    "M9.88 9.88A2 2 0 0 1 9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16h11",
    "m2 2 20 20"
  ],
  plus: ["M5 12h14", "M12 5v14"],
  "sliders-horizontal": [
    "M21 4h-7",
    "M10 4H3",
    "M14 2v4",
    "M21 12h-9",
    "M8 12H3",
    "M8 10v4",
    "M21 20h-5",
    "M12 20H3",
    "M16 18v4"
  ],
  square: ["M5 5h14v14H5z"],
  type: ["M4 7V4h16v3", "M9 20h6", "M12 4v16"],
  "trash-2": ["M3 6h18", "M8 6V4h8v2", "M19 6l-1 14H6L5 6", "M10 11v6", "M14 11v6"],
  upload: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M17 8l-5-5-5 5", "M12 3v12"],
  "volume-2": ["M11 5 6 9H2v6h4l5 4z", "M19.07 4.93a10 10 0 0 1 0 14.14", "M15.54 8.46a5 5 0 0 1 0 7.07"],
  "volume-x": ["M11 5 6 9H2v6h4l5 4z", "m22 9-6 6", "m16 9 6 6"],
  x: ["M18 6 6 18", "m6 6 12 12"]
};
</script>

<template>
  <svg
    class="app-icon"
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="props.strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="path in ICON_PATHS[props.name]" :key="path" :d="path" />
  </svg>
</template>
