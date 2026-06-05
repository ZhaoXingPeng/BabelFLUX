import { nextTick, onMounted, onUnmounted, ref, type Ref, watch } from "vue";
import { gsap } from "gsap";
import { ScrollToPlugin } from "gsap/ScrollToPlugin";
import { DUR, EASE, shouldReduceMotion } from "./motion";

gsap.registerPlugin(ScrollToPlugin);

export function useStickyFollow(
  container: Ref<HTMLElement | null>,
  signature: () => string,
  options: { block?: "center" | "start" } = {}
) {
  const following = ref(true);
  let removeListener: (() => void) | null = null;
  let userInteracted = false;

  function isNearBottom(element: HTMLElement): boolean {
    return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  }

  function followLatest() {
    const element = container.value;
    const active = element?.querySelector<HTMLElement>("[data-active='true']");
    if (!element || !active) return;
    userInteracted = false;
    following.value = true;
    if (shouldReduceMotion()) {
      active.scrollIntoView({ block: options.block ?? "center" });
      return;
    }
    const target = options.block === "start" ? active.offsetTop - 12 : active.offsetTop - element.clientHeight / 2 + active.clientHeight / 2;
    gsap.to(element, {
      scrollTo: { y: Math.max(0, target) },
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
      if (following.value) followLatest();
    },
    { flush: "post" }
  );

  return { following, followLatest };
}
