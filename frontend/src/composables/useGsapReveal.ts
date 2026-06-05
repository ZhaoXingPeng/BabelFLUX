import { onMounted, onUnmounted, type Ref } from "vue";
import { gsap } from "gsap";

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
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    ctx = gsap.context(() => {
      gsap.from("[data-reveal]", {
        autoAlpha: 0,
        y: options.y ?? 14,
        duration: options.duration ?? 0.55,
        ease: "power2.out",
        stagger: options.stagger ?? 0.08
      });
    }, element);
  });

  onUnmounted(() => {
    ctx?.revert();
  });
}
