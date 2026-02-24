import type { Transition } from "framer-motion";

/** Calm, literary-feeling spring — default for most UI transitions. */
export const softSpring: Transition = {
  type: "spring",
  duration: 0.35,
  stiffness: 120,
  damping: 20,
};

/** Snappy micro-interaction — buttons, toggles, small state changes. */
export const microRebound: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 20,
};

/** No bounce — page transitions and prose fade-ins. */
export const smooth: Transition = {
  type: "spring",
  duration: 0.4,
  bounce: 0,
};

/** Gentle 15% bounce — dropdown menus, popovers. */
export const snappy: Transition = {
  type: "spring",
  duration: 0.4,
  bounce: 0.15,
};
