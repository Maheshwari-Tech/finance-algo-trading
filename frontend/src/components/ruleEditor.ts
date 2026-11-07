import { ApiError } from "../api/client";
import type { BuilderCatalog, Condition, OperandSpec, TradeRule } from "../api/types";
import { h } from "../lib/dom";
import { rulesNow, saveRule } from "../lib/savedStrategies";
import { ui } from "../lib/uiConfig";

/** "Buy 1 lot when 1-day change % is above 1" - for the plain-English summaries. */
export function describeRule(r: TradeRule, catalog: BuilderCatalog): string {
  const label = (o: OperandSpec): string => {
    if (o.kind === "price") return catalog.price_fields.find((f) => f.value === o.field)?.label ?? "Close";
    if (o.kind === "value") return String(o.value ?? 0);
    const info = catalog.operands.find((x) => x.kind === o.kind)!;
    return `${info.label.replace(/\s*\(days\)|\s+days|\s+over days/i, "").replace(" of previous", "")} (${o.period ?? info.default_period}d)`;
  };
  const cond = (c: Condition) => `${label(c.left)} ${catalog.operators.find((o) => o.value === c.op)?.label} ${label(c.right)}`;
  const head = `${r.action === "buy" ? "Buy" : "Sell"} ${r.lots} lot${r.lots === 1 ? "" : "s"}`;
  return r.conditions.length ? `${head} when ${r.conditions.map(cond).join(r.match === "all" ? " and " : " or ")}` : `${head} every day`;
}

const body = (r: TradeRule) => JSON.stringify({ name: (r.name ?? "").trim(), action: r.action, lots: r.lots, match: r.match, conditions: r.conditions });

/** One rule: name, buy/sell, lots, all/any, conditions, and saving it to your account. */
export class RuleEditor {
  readonly el = h("section");
  private msg = h("p", { class: "msg" });

  constructor(
    private catalog: BuilderCatalog, public rule: TradeRule,
    private opts: { onChange: () => void; onStructure?: () => void; onRemove?: () => void; onAction?: () => void; saveButton?: boolean },
  ) {
    this.render();
  }

  /** Changed compared with the saved version of this rule. */
  get dirty(): boolean {
    const saved = this.rule.id ? rulesNow().find((x) => x.id === this.rule.id) : undefined;
    return !!saved && body(this.rule) !== body(saved);
  }

  private say(text: string, kind: "ok" | "error") { this.msg.textContent = text; this.msg.className = `msg ${kind}`; }

  private changed() { this.renderFooter(); this.opts.onChange(); }
  private structural() { this.render(); (this.opts.onStructure ?? this.opts.onChange)(); }

  private footer = h("div", { class: "rule-foot" });

  private render() {
    const r = this.rule, L = this.catalog.limits;
    const action = h("select", { class: `action ${r.action}`, title: "Swap between buy and sell", on: { change: (e) => {
      r.action = (e.target as HTMLSelectElement).value as "buy" | "sell";
      if (this.opts.onAction) this.opts.onAction(); else this.structural();
    } } }, h("option", { value: "buy", selected: r.action === "buy" }, "Buy"), h("option", { value: "sell", selected: r.action === "sell" }, "Sell"));
    const lots = h("input", { type: "number", class: "mini", min: L.lots.min, max: L.lots.max, step: 1, value: String(r.lots), on: { input: (e) => {
      const v = (e.target as HTMLInputElement).valueAsNumber;
      if (Number.isInteger(v) && v >= L.lots.min && v <= L.lots.max) { r.lots = v; this.changed(); }
    } } });
    // Rule names are only edited where rules are saved on their own (Test a rule page).
    const name = this.opts.saveButton === false ? null : h("input", { class: "rule-name", value: r.name ?? "", maxLength: 60, placeholder: "Rule name (to save it)",
      on: { input: (e) => { r.name = (e.target as HTMLInputElement).value; this.changed(); } } });
    const match = h("select", { class: "inline", on: { change: (e) => { r.match = (e.target as HTMLSelectElement).value as "all" | "any"; this.changed(); } } },
      h("option", { value: "all", selected: r.match === "all" }, "all"), h("option", { value: "any", selected: r.match === "any" }, "any"));

    this.el.className = `group ${r.action}`;
    this.el.replaceChildren(
      h("div", { class: "group-head" }, action, lots, h("span", { class: "sub" }, "lot(s)"),
        this.opts.onRemove && h("button", { type: "button", class: "icon-btn push", title: "Remove this rule from the strategy", on: { click: () => this.opts.onRemove!() } }, "×")),
      ...(name ? [name] : []),
      r.conditions.length
        ? h("div", { class: "group-sub" }, h("span", { class: "sub" }, "when"), match, h("span", { class: "sub" }, "of these are true"))
        : h("p", { class: "hint tight" }, "No condition: this order is placed every day."),
      ...r.conditions.map((c, i) => this.conditionRow(c, i)),
      h("button", { type: "button", class: "btn ghost add", on: { click: () => {
        if (r.conditions.length >= L.conditions_per_rule) return;
        r.conditions.push(structuredClone(ui().new_condition[r.action]));
        this.structural();
      } } }, "+ Add condition"),
      this.footer, this.msg);
    this.renderFooter();
  }

  private renderFooter() {
    if (this.opts.saveButton === false) { this.footer.replaceChildren(); return; }
    const r = this.rule;
    const original = r.id ? rulesNow().find((x) => x.id === r.id) : undefined;
    const used = original?.used_by ?? [];
    // A new name means a new rule: the original stays as it was.
    const asNew = !!original && (r.name ?? "").trim() !== original.name;
    const save = async () => {
      try {
        const s = await saveRule(structuredClone(asNew ? { ...r, id: undefined } : r));
        r.id = s.id; r.name = s.name;
        this.render();
        this.say(asNew ? `Saved as a new rule "${s.name}". "${original!.name}" is unchanged.`
          : used.length ? `Saved. Updated in: ${used.join(", ")}` : "Saved to your rules", "ok");
        this.opts.onChange();
      } catch (err) { this.say(err instanceof ApiError ? err.message : "Could not save the rule", "error"); }
    };
    this.footer.replaceChildren(!original
      ? h("div", { class: "rule-status" }, h("span", { class: "sub" }, "Not saved"),
          h("button", { type: "button", class: "btn ghost", on: { click: save } }, "Save rule"))
      : asNew
        ? h("div", { class: "rule-status" }, h("span", { class: "sub" }, `New name: saves a new rule, "${original.name}" stays`),
            h("button", { type: "button", class: "btn ghost", on: { click: save } }, "Save as new rule"))
        : h("div", { class: "rule-status" },
            h("span", { class: "sub" }, this.dirty ? "Changed, not saved yet" : "Saved rule", used.length ? ` · used by ${used.join(", ")}` : ""),
            h("button", { type: "button", class: "btn ghost", disabled: !this.dirty, on: { click: save } }, used.length > 1 ? "Save changes (all strategies)" : "Save changes")));
  }


  private conditionRow(c: Condition, index: number): HTMLElement {
    const op = h("select", { on: { change: (e) => { c.op = (e.target as HTMLSelectElement).value; this.changed(); } } },
      this.catalog.operators.map((o) => h("option", { value: o.value, selected: o.value === c.op }, o.label)));
    return h("div", { class: "cond" },
      this.operandEditor(c.left), op, this.operandEditor(c.right),
      h("button", { type: "button", class: "icon-btn", title: "Remove condition", on: { click: () => { this.rule.conditions.splice(index, 1); this.structural(); } } }, "×"));
  }

  private operandEditor(o: OperandSpec): HTMLElement {
    const code = (x: OperandSpec) => (x.kind === "price" ? `price:${x.field}` : x.kind);
    const choices = [
      ...this.catalog.price_fields.map((f) => ({ code: `price:${f.value}`, label: f.label })),
      ...this.catalog.operands.filter((x) => x.kind !== "price").map((x) => ({ code: x.kind, label: x.label, help: x.help })),
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
    } } }, choices.map((ch) => h("option", { value: ch.code, selected: ch.code === code(o), title: "help" in ch ? ch.help ?? "" : "" }, ch.label)));

    const info = this.catalog.operands.find((x) => x.kind === o.kind);
    if (info?.help) kind.title = info.help;
    const number = (value: number, min: number, max: number, set: (v: number) => void) => h("input", {
      type: "number", class: "mini", value: String(value), min, max, step: "any",
      on: { input: (e) => { const v = (e.target as HTMLInputElement).valueAsNumber; if (!Number.isNaN(v)) { set(v); this.changed(); } } },
    });
    return h("div", { class: "operand" }, kind,
      info?.uses_period && number(o.period ?? info.default_period ?? this.catalog.limits.period.min, this.catalog.limits.period.min, this.catalog.limits.period.max, (v) => { o.period = Math.round(v); }),
      info?.uses_value && number(o.value ?? 0, -1e9, 1e9, (v) => { o.value = v; }));
  }
}
