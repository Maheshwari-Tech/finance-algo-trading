import type { UiConfig } from "../api/types";

let current: UiConfig | null = null;

export const setUiConfig = (cfg: UiConfig) => { current = cfg; };

export function ui(): UiConfig {
  if (!current) throw new Error("UI config not loaded");
  return current;
}
