import type { RuleSet } from "../api/types";

const KEY = "bt-saved-strategies-v2";

export function listSaved(): RuleSet[] {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "[]") as RuleSet[]; } catch { return []; }
}

export function saveStrategy(rules: RuleSet): void {
  const others = listSaved().filter((r) => r.name !== rules.name);
  localStorage.setItem(KEY, JSON.stringify([...others, rules]));
}

export function deleteStrategy(name: string): void {
  localStorage.setItem(KEY, JSON.stringify(listSaved().filter((r) => r.name !== name)));
}
