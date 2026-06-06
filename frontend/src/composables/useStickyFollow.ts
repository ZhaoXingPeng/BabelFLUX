import { nextTick, onMounted, onUnmounted, ref, type Ref, watch } from "vue";
import { gsap } from "gsap";
import { ScrollToPlugin } from "gsap/ScrollToPlugin";
import { DUR, EASE, shouldReduceMotion } from "./motion";

gsap.registerPlugin(ScrollToPlugin);

export function useStickyFollow(
  container: Ref<HTMLElement | null>,
  signature: () => string,
  options: { block?: "center" | "start"; force?: boolean } = {}
) {
  const following = ref(true);
  let removeListener: (() => void) | null = null;
  let userInteracted = false;
  let activeTween: gsap.core.Tween | null = null;
  // 上一次滚动目标位置；用于「合并去抖」，避免每个 partial 字符都重启补间造成的持续滚动抖动。
  let lastTarget = -1;
  const FOLLOW_THRESHOLD = 28;

  function isNearBottom(element: HTMLElement): boolean {
    return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }

  function followLatest() {
    const element = container.value;
    const cards = Array.from(element?.querySelectorAll<HTMLElement>(".sentence-pair-card") ?? []);
    const active = element?.querySelector<HTMLElement>("[data-active='true']") ?? cards[cards.length - 1];
    if (!element || !active) return;
    userInteracted = false;
    following.value = true;
    const rawTarget =
      options.block === "start"
        ? active.offsetTop - 12
        : active.offsetTop - element.clientHeight / 2 + active.clientHeight / 2;
    const target = Math.max(0, Math.min(rawTarget, element.scrollHeight - element.clientHeight));
    // 目标几乎没动（当前句逐字增长时的微小位移）就跳过，让正在进行的滚动平滑走完；
    // 累计位移超过阈值或切到新句（大跳跃）时才发起一次新的补间 → 平滑分步跟随，不再逐字抖动。
    if (lastTarget >= 0 && Math.abs(target - lastTarget) < FOLLOW_THRESHOLD) return;
    lastTarget = target;
    if (shouldReduceMotion()) {
      activeTween?.kill();
      activeTween = null;
      element.scrollTop = target;
      return;
    }
    activeTween = gsap.to(element, {
      scrollTo: { y: target },
      duration: DUR.base,
      ease: EASE,
      overwrite: "auto"
    });
  }

  onMounted(() => {
    const element = container.value;
    if (!element) return;
    const markUserIntent = () => {
      userInteracted = true;
    };
    const onScroll = () => {
      if (options.force) {
        following.value = true;
        return;
      }
      if (!userInteracted) return;
      following.value = isNearBottom(element);
    };
    element.addEventListener("wheel", markUserIntent, { passive: true });
    element.addEventListener("touchstart", markUserIntent, { passive: true });
    element.addEventListener("pointerdown", markUserIntent, { passive: true });
    element.addEventListener("scroll", onScroll, { passive: true });
    removeListener = () => {
      element.removeEventListener("wheel", markUserIntent);
      element.removeEventListener("touchstart", markUserIntent);
      element.removeEventListener("pointerdown", markUserIntent);
      element.removeEventListener("scroll", onScroll);
    };
    nextTick(() => followLatest());
  });

  onUnmounted(() => {
    removeListener?.();
  });

  watch(
    signature,
    async () => {
      await nextTick();
      if (options.force || following.value) followLatest();
    },
    { flush: "post" }
  );

  return { following, followLatest };
}
