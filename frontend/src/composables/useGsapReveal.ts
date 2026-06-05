import { onMounted, onUnmounted, type Ref } from "vue";
import { gsap } from "gsap";
import { DUR, EASE, STAGGER, shouldReduceMotion } from "./motion";

interface RevealOptions {
  duration?: number;
  stagger?: number;
  y?: number;
}

export function useGsapReveal(scope: Ref<HTMLElement | null>, options: RevealOptions = {}) {
  let ctx: ReturnType<typeof gsap.context> | null = null;

  onMounted(() => {
    const element = scope.value;
    if (!element) return;
    if (shouldReduceMotion()) return;

    ctx = gsap.context(() => {
      gsap.from("[data-reveal]", {
        autoAlpha: 0,
        y: options.y ?? 14,
        duration: options.duration ?? DUR.base,
        ease: EASE,
        stagger: options.stagger ?? STAGGER
      });
    }, element);
  });

  onUnmounted(() => {
    ctx?.revert();
  });
}
