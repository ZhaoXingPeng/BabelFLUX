import { nextTick, type Ref } from "vue";
import { gsap } from "gsap";
import { Flip } from "gsap/Flip";
import { DUR, EASE, shouldReduceMotion } from "./motion";

gsap.registerPlugin(Flip);

export async function withFlipMode(scope: Ref<HTMLElement | null>, selector: string, mutate: () => void) {
  const element = scope.value;
  if (!element || shouldReduceMotion()) {
    mutate();
    await nextTick();
    return;
  }

  const state = Flip.getState(element.querySelectorAll(selector));
  mutate();
  await nextTick();
  Flip.from(state, {
    absolute: true,
    duration: DUR.base,
    ease: EASE,
    scale: false
  });
}
