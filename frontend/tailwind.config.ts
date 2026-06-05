import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        ink: "#0e1f2f",
        salt: "#f7fbf8",
        tide: "#20c7a7",
        warning: "#f0a43a",
        danger: "#e85d5d"
      },
      fontFamily: {
        sans: ["Avenir Next", "Noto Sans SC", "sans-serif"],
        display: ["Space Grotesk", "Noto Sans SC", "sans-serif"]
      }
    }
  },
  plugins: []
} satisfies Config;
