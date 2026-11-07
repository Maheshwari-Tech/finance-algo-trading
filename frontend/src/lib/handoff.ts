import type { BacktestRequest } from "../api/types";

/** Carries the current settings from one page to another ("Apply this strategy", "Open in Strategy"). In memory only. */
let pending: BacktestRequest | null = null;

export function handOff(req: BacktestRequest, to: string) {
  pending = structuredClone(req);
  location.hash = to;
}

export function takeHandOff(): BacktestRequest | undefined {
  const r = pending ?? undefined;
  pending = null;
  return r;
}
