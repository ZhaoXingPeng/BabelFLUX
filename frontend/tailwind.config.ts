import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        paper: "#FAF8F3",
        surface: "#FFFFFF",
        ink: "#17212B",
        "ink-soft": "#5B6470",
        line: "#E6E2D8",
        brand: "#2F5D50",
        "brand-deep": "#244A40",
        accent: "#C8884A",
        stage: "#14161A",
        "stage-soft": "#1C1F26",
        "stage-line": "#2A2E37",
        "stage-src": "#C9CDD4",
        "stage-dst": "#FFFFFF",
        "stage-accent": "#E0A458",
        "stage-ok": "#5FB48A",
        "stage-muted": "#6B7280"
      },
      fontFamily: {
        sans: [
          '"Geist Variable"',
          '"HarmonyOS Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          '"Noto Sans SC"',
          "system-ui",
          "sans-serif"
        ],
        display: ['"Fraunces"', '"Source Han Serif SC"', '"Songti SC"', "Georgia", "serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"]
      },
      boxShadow: {
        soft: "0 1px 2px rgba(20,22,26,.04), 0 8px 24px rgba(20,22,26,.06)",
        stage: "0 12px 34px rgba(0,0,0,.32)"
      },
      animation: {
        breathe: "breathe 2.4s ease-in-out infinite"
      },
      keyframes: {
        breathe: {
          "0%,100%": { boxShadow: "0 0 0 1px rgba(224,164,88,.85), 0 0 0 0 rgba(224,164,88,0)" },
          "50%": { boxShadow: "0 0 0 1px rgba(224,164,88,.85), 0 0 22px 2px rgba(224,164,88,.22)" }
        }
      }
    }
  },
  plugins: []
} satisfies Config;
