import { api } from "../api/client";
import type { RuleSet, SavedRule, SavedStrategy, TradeRule } from "../api/types";

/** The signed-in user's saved rules and strategies (server side), cached after the first load.
 *  Strategies refer to saved rules by id, so changing a saved rule changes every strategy that uses it. */
let rules: SavedRule[] | null = null;
let strategies: SavedStrategy[] | null = null;
const listeners = new Set<() => void>();

export async function loadSaved(force = false): Promise<void> {
  if (!rules || !strategies || force) [rules, strategies] = await Promise.all([api.rules(), api.saved()]);
}

export const rulesNow = (): SavedRule[] => rules ?? [];
export const strategiesNow = (): SavedStrategy[] => strategies ?? [];
/** Saved strategies as rule sets, ready to run. */
export const savedNow = (): RuleSet[] => strategiesNow().map((s) => ({ name: s.name, rules: s.rules }));

export function onSavedChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const publish = () => listeners.forEach((fn) => fn());

/** Save a rule: creates it, or updates it when it already has an id. Returns the saved version (with its id). */
export async function saveRule(rule: TradeRule): Promise<SavedRule> {
  const { id, ...body } = rule;
  rules = id ? await api.updateRule(id, body) : await api.createRule(body);
  strategies = await api.saved();  // strategies show the new version of the rule
  publish();
  return rules.find((r) => (id ? r.id === id : r.name === (body.name ?? "").trim()))!;
}

export async function deleteRule(id: number): Promise<void> { rules = await api.deleteRule(id); publish(); }

export async function saveStrategy(name: string, ruleIds: number[]): Promise<void> {
  strategies = await api.save({ name, rule_ids: ruleIds });
  rules = await api.rules();  // "used by" changes
  publish();
}

export async function deleteStrategy(name: string): Promise<void> {
  strategies = await api.unsave(name);
  rules = await api.rules();
  publish();
}

export function clearSavedCache() { rules = null; strategies = null; }
