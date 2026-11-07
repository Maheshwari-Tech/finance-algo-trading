import { ApiError } from "../api/client";
import type { BuilderCatalog, RuleSet } from "../api/types";
import { h } from "../lib/dom";
import { deleteStrategy, rulesNow, saveRule, saveStrategy, strategiesNow } from "../lib/savedStrategies";
import { ui } from "../lib/uiConfig";
import { describeRule, RuleEditor } from "./ruleEditor";

type Action = "buy" | "sell";

/** A strategy = a name + buy rules + sell rules. Rules can be loaded from (and saved to) your saved rules. */
export class RuleBuilder {
  readonly el = h("div", { class: "builder" });
  private editors: RuleEditor[] = [];
  private refreshPreview: () => void = () => {};
  private msg = h("p", { class: "msg" });

  constructor(private catalog: BuilderCatalog, public rules: RuleSet, private onChange: (rules: RuleSet) => void) {
    this.render();
  }

  get isComplete(): boolean { return this.rules.rules.length > 0; }

  /** Replace the strategy being edited (e.g. a saved strategy picked elsewhere). */
  load(rules: RuleSet) { this.rules = rules; this.structural(); }

  private changed() { this.refreshPreview(); this.onChange(this.rules); }
  private structural() { this.render(); this.onChange(this.rules); }
  private say(text: string, kind: "ok" | "error") { this.msg.textContent = text; this.msg.className = `msg ${kind}`; }

  private render() {
    const preview = h("div", { class: "sentence" });
    this.refreshPreview = () => preview.replaceChildren(...(this.rules.rules.length
      ? this.rules.rules.map((r) => h("p", { class: r.action === "buy" ? "buy-text" : "sell-text" }, describeRule(r, this.catalog)))
      : [h("p", {}, "Add a buy rule and a sell rule to get started.")]));
    this.editors = [];
    this.el.replaceChildren(
      h("label", { class: "field" }, h("span", {}, "Start from an example"), this.templatePicker()),
      h("label", { class: "field" }, h("span", {}, "Strategy name"),
        h("input", { value: this.rules.name, maxLength: 60, on: { input: (e) => { this.rules.name = (e.target as HTMLInputElement).value; this.changed(); } } })),
      this.section("buy"), this.section("sell"),
      h("div", { class: "sentence-box" }, h("span", { class: "sentence-title" }, "In plain English"), preview),
      this.strategyControls());
    this.refreshPreview();
  }

  private section(action: Action): HTMLElement {
    const mine = this.rules.rules.map((r, i) => ({ r, i })).filter((x) => x.r.action === action);
    const full = this.rules.rules.length >= this.catalog.limits.rules;
    const savedOfKind = rulesNow().filter((r) => r.action === action);
    const loader = h("select", { class: "load-rule", disabled: full || !savedOfKind.length, on: { change: (e) => {
      const id = Number((e.target as HTMLSelectElement).value);
      const s = savedOfKind.find((x) => x.id === id);
      if (!s) return;
      if (this.rules.rules.some((r) => r.id === id)) { this.say(`"${s.name}" is already in this strategy`, "error"); this.render(); return; }
      const { used_by: _ignored, ...rule } = s;
      this.rules.rules.push(structuredClone(rule));
      this.structural();
    } } }, h("option", { value: "" }, savedOfKind.length ? `Load a saved ${action} rule...` : `No saved ${action} rules yet`),
      savedOfKind.map((s) => h("option", { value: String(s.id) }, s.name)));
    return h("div", { class: `rule-section ${action}` },
      h("h3", { class: "section-title" }, action === "buy" ? "Buy rules" : "Sell rules"),
      ...mine.map(({ r, i }) => {
        const ed = new RuleEditor(this.catalog, r, {
          onChange: () => this.changed(),
          onStructure: () => this.changed(),
          onAction: () => this.structural(),  // moves the rule to the other section
          onRemove: () => { this.rules.rules.splice(i, 1); this.structural(); },
          saveButton: false,
        });
        this.editors.push(ed);
        return ed.el;
      }),
      h("div", { class: "section-actions" },
        h("button", { type: "button", class: "btn ghost add", disabled: full, on: { click: () => {
          this.rules.rules.push(structuredClone({ ...ui().new_rule, action, conditions: [structuredClone(ui().new_condition[action])] }));
          this.structural();
        } } }, action === "buy" ? "+ Add buy rule" : "+ Add sell rule"),
        loader));
  }

  private templatePicker(): HTMLElement {
    return h("select", { on: { change: (e) => {
      const t = ui().rule_templates[Number((e.target as HTMLSelectElement).value)];
      if (t) { this.rules = structuredClone(t); this.structural(); }
    } } }, h("option", { value: "" }, "Choose..."), ui().rule_templates.map((t, i) => h("option", { value: String(i) }, t.name)));
  }

  /** Save strategy: saves new rules (auto-named if left empty), updates changed saved rules, then the strategy. */
  private async saveAll() {
    const name = this.rules.name.trim();
    if (!name) { this.say("Give the strategy a name first", "error"); return; }
    if (!this.rules.rules.length) { this.say("Add at least one rule", "error"); return; }
    const taken = new Set(rulesNow().map((r) => r.name));
    const autoName = (r: (typeof this.rules.rules)[number]) => {
      const base = `${name} · ${r.action === "buy" ? "Buy" : "Sell"}`;
      let n = 1;
      while (taken.has(`${base} ${n}`)) n++;
      taken.add(`${base} ${n}`);
      return `${base} ${n}`;
    };
    try {
      for (const ed of this.editors) {
        const r = ed.rule;
        if (!r.id) {
          if (!(r.name ?? "").trim()) r.name = autoName(r);
          const s = await saveRule(structuredClone(r));
          r.id = s.id; r.name = s.name;
        } else if (ed.dirty) {
          await saveRule(structuredClone(r));
        }
      }
      await saveStrategy(name, this.rules.rules.map((r) => r.id!));
      this.render();
      this.say(`Saved strategy "${name}"`, "ok");
    } catch (err) { this.say(err instanceof ApiError ? err.message : "Could not save", "error"); }
  }

  private strategyControls(): HTMLElement {
    const exists = strategiesNow().some((s) => s.name === this.rules.name.trim());
    return h("div", { class: "saved-box" },
      h("span", { class: "sentence-title" }, "Saved to your account"),
      h("div", { class: "saved" },
        h("button", { type: "button", class: "btn ghost", on: { click: () => void this.saveAll() } }, exists ? "Save strategy (replace)" : "Save strategy"),
        exists && h("button", { type: "button", class: "btn ghost", on: { click: async () => {
          if (!confirm(`Delete saved strategy "${this.rules.name}"? Its rules stay saved.`)) return;
          await deleteStrategy(this.rules.name.trim()); this.render(); this.say("Strategy deleted", "ok");
        } } }, "Delete strategy")),
      h("p", { class: "hint tight" }, "Saves the strategy and its rules. Saved strategies appear in the Rule list at the top; saved rules can be loaded into any strategy."),
      this.msg);
  }
}

