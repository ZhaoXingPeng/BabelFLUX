export const EASE = "power2.out";
export const EASE_SOFT = "power1.inOut";
export const DUR = {
  micro: 0.18,
  base: 0.42,
  slow: 0.8
} as const;
export const STAGGER = 0.08;

export function shouldReduceMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}
