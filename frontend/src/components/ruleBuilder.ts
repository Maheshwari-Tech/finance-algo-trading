import type { BuilderCatalog, Condition, OperandSpec, RuleSet, TradeRule } from "../api/types";
import { h } from "../lib/dom";
import { ui } from "../lib/uiConfig";
import { deleteStrategy, listSaved, saveStrategy } from "../lib/savedStrategies";

/** No-code strategy editor: a list of "<Buy|Sell> <lots> when <conditions>" rules. */
export class RuleBuilder {
  readonly el = h("div", { class: "builder" });
  private refreshPreview: () => void = () => {};

  constructor(private catalog: BuilderCatalog, public rules: RuleSet, private onChange: (rules: RuleSet) => void) {
    this.render();
  }

  get isComplete(): boolean { return this.rules.rules.length > 0; }

  private changed() { this.onChange(this.rules); }
  private structural() { this.render(); this.changed(); }

  private render() {
    const preview = h("div", { class: "sentence" });
    this.refreshPreview = () => preview.replaceChildren(...this.sentence());
    this.el.replaceChildren(
      h("label", { class: "field" }, h("span", {}, "Start from an example"), this.templatePicker()),
      h("label", { class: "field" }, h("span", {}, "Strategy name"),
        h("input", { value: this.rules.name, maxLength: 60, on: { input: (e) => { this.rules.name = (e.target as HTMLInputElement).value; this.changed(); } } })),
      ...this.rules.rules.map((r, i) => this.ruleCard(r, i)),
      h("button", { type: "button", class: "btn ghost add", on: { click: () => {
        if (this.rules.rules.length >= this.catalog.limits.rules) return;
        this.rules.rules.push(structuredClone({ ...ui().new_rule, conditions: [structuredClone(ui().new_condition[ui().new_rule.action])] }));
        this.structural();
      } } }, "+ Add rule"),
      h("div", { class: "sentence-box" }, h("span", { class: "sentence-title" }, "In plain English"), preview),
      this.savedControls());
    this.refreshPreview();
  }

  private sentence(): HTMLElement[] {
    if (!this.rules.rules.length) return [h("p", {}, "Add a rule to get started.")];
    return this.rules.rules.map((r) => {
      const cond = r.conditions.length ? r.conditions.map((c) => this.describe(c)).join(r.match === "all" ? " and " : " or ") : "every day";
      return h("p", { class: r.action === "buy" ? "buy-text" : "sell-text" },
        h("b", {}, `${r.action === "buy" ? "Buy" : "Sell"} ${r.lots} lot${r.lots === 1 ? "" : "s"}`), r.conditions.length ? " when " : " ", cond);
    });
  }

  private describe(c: Condition): string {
    const label = (o: OperandSpec): string => {
      if (o.kind === "price") return this.catalog.price_fields.find((f) => f.value === o.field)?.label ?? "Close";
      if (o.kind === "value") return String(o.value ?? 0);
      const info = this.catalog.operands.find((x) => x.kind === o.kind)!;
      return `${info.label.replace(/\s*\(days\)|\s+days|\s+over days/i, "").replace(" of previous", "")} (${o.period ?? info.default_period}d)`;
    };
    return `${label(c.left)} ${this.catalog.operators.find((o) => o.value === c.op)?.label} ${label(c.right)}`;
  }

  private templatePicker(): HTMLElement {
    return h("select", { on: { change: (e) => {
      const t = ui().rule_templates[Number((e.target as HTMLSelectElement).value)];
      if (t) { this.rules = structuredClone(t); this.structural(); }
    } } }, h("option", { value: "" }, "Choose..."), ui().rule_templates.map((t, i) => h("option", { value: String(i) }, t.name)));
  }

  private ruleCard(r: TradeRule, index: number): HTMLElement {
    const action = h("select", { class: `action ${r.action}`, on: { change: (e) => { r.action = (e.target as HTMLSelectElement).value as "buy" | "sell"; this.structural(); } } },
      h("option", { value: "buy", selected: r.action === "buy" }, "Buy"), h("option", { value: "sell", selected: r.action === "sell" }, "Sell"));
    const lots = h("input", { type: "number", class: "mini", min: this.catalog.limits.lots.min, max: this.catalog.limits.lots.max, step: 1, value: String(r.lots), on: { input: (e) => {
      const v = (e.target as HTMLInputElement).valueAsNumber;
      if (Number.isInteger(v) && v >= this.catalog.limits.lots.min && v <= this.catalog.limits.lots.max) { r.lots = v; this.refreshPreview(); this.changed(); }
    } } });
    const match = h("select", { class: "inline", on: { change: (e) => { r.match = (e.target as HTMLSelectElement).value as "all" | "any"; this.refreshPreview(); this.changed(); } } },
      h("option", { value: "all", selected: r.match === "all" }, "all"), h("option", { value: "any", selected: r.match === "any" }, "any"));

    return h("section", { class: `group ${r.action}` },
      h("div", { class: "group-head" }, action, lots, h("span", { class: "sub" }, "lot(s)"),
        h("button", { type: "button", class: "icon-btn push", title: "Remove rule", on: { click: () => { this.rules.rules.splice(index, 1); this.structural(); } } }, "×")),
      r.conditions.length
        ? h("div", { class: "group-sub" }, h("span", { class: "sub" }, "when"), match, h("span", { class: "sub" }, "of these are true"))
        : h("p", { class: "hint tight" }, "No condition: this order is placed every day."),
      ...r.conditions.map((c, i) => this.conditionRow(r, c, i)),
      h("button", { type: "button", class: "btn ghost add", on: { click: () => {
        if (r.conditions.length >= this.catalog.limits.conditions_per_rule) return;
        r.conditions.push(structuredClone(ui().new_condition[r.action]));
        this.structural();
      } } }, "+ Add condition"));
  }

  private conditionRow(r: TradeRule, c: Condition, index: number): HTMLElement {
    const op = h("select", { on: { change: (e) => { c.op = (e.target as HTMLSelectElement).value; this.refreshPreview(); this.changed(); } } },
      this.catalog.operators.map((o) => h("option", { value: o.value, selected: o.value === c.op }, o.label)));
    return h("div", { class: "cond" },
      this.operandEditor(c.left), op, this.operandEditor(c.right),
      h("button", { type: "button", class: "icon-btn", title: "Remove condition", on: { click: () => { r.conditions.splice(index, 1); this.structural(); } } }, "×"));
  }

  private operandEditor(o: OperandSpec): HTMLElement {
    const code = (x: OperandSpec) => (x.kind === "price" ? `price:${x.field}` : x.kind);
    const choices = [
      ...this.catalog.price_fields.map((f) => ({ code: `price:${f.value}`, label: f.label })),
      ...this.catalog.operands.filter((x) => x.kind !== "price").map((x) => ({ code: x.kind, label: x.label })),
    ];
    const kind = h("select", { on: { change: (e) => {
      const v = (e.target as HTMLSelectElement).value;
      for (const k of ["period", "value", "field"] as const) delete o[k];
      if (v.startsWith("price:")) { o.kind = "price"; o.field = v.slice(6); } else {
        const info = this.catalog.operands.find((x) => x.kind === v)!;
        o.kind = v;
        if (info.uses_period) o.period = info.default_period ?? this.catalog.limits.period.min;
        if (info.uses_value) o.value = 0;
      }
      this.structural();
    } } }, choices.map((ch) => h("option", { value: ch.code, selected: ch.code === code(o) }, ch.label)));

    const info = this.catalog.operands.find((x) => x.kind === o.kind);
    const number = (value: number, min: number, max: number, set: (v: number) => void) => h("input", {
      type: "number", class: "mini", value: String(value), min, max, step: "any",
      on: { input: (e) => { const v = (e.target as HTMLInputElement).valueAsNumber; if (!Number.isNaN(v)) { set(v); this.refreshPreview(); this.changed(); } } },
    });
    return h("div", { class: "operand" }, kind,
      info?.uses_period && number(o.period ?? info.default_period ?? this.catalog.limits.period.min, this.catalog.limits.period.min, this.catalog.limits.period.max, (v) => { o.period = Math.round(v); }),
      info?.uses_value && number(o.value ?? 0, -1e9, 1e9, (v) => { o.value = v; }));
  }

  private savedControls(): HTMLElement {
    const saved = listSaved();
    const load = h("select", { on: { change: (e) => {
      const r = saved.find((s) => s.name === (e.target as HTMLSelectElement).value);
      if (r) { this.rules = structuredClone(r); this.structural(); }
    } } }, h("option", { value: "" }, saved.length ? "Load saved..." : "No saved strategies"), saved.map((s) => h("option", { value: s.name }, s.name)));
    return h("div", { class: "saved" }, load,
      h("button", { type: "button", class: "btn ghost", on: { click: () => {
        if (this.rules.name.trim()) { saveStrategy(structuredClone(this.rules)); this.render(); }
      } } }, "Save"),
      saved.length > 0 && h("button", { type: "button", class: "btn ghost", on: { click: () => {
        const sel = (load as HTMLSelectElement).value;
        if (sel && confirm(`Delete saved strategy "${sel}"?`)) { deleteStrategy(sel); this.render(); }
      } } }, "Delete"));
  }
}

