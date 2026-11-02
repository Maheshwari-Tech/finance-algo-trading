import type { BacktestRequest, BuilderCatalog, ParamValues, StrategyCatalog, StrategyInfo, SymbolInfo } from "../api/types";
import { ui } from "../lib/uiConfig";
import { RuleBuilder } from "./ruleBuilder";

const CUSTOM = "__custom__";
import { debounce, h } from "../lib/dom";

/** Builds the strategy form. Parameter inputs are generated from the backend's strategy metadata. */
export class Controls {
  readonly el = h("aside", { class: "panel controls" });
  private state: BacktestRequest;
  private custom = false;
  private readonly emit = debounce(() => { if (!this.isCustom || this.builder.isComplete) this.onChange(this.payload()); }, 250);

  constructor(
    private symbols: SymbolInfo[], private catalog: StrategyCatalog, builder: BuilderCatalog,
    private onChange: (req: BacktestRequest) => void,
  ) {
    const d = ui().defaults;
    this.state = {
      ...d, symbol: symbols[0].symbol, params: defaults(catalog.strategies[0]),
      strategy_id: d.strategy_id === "custom" ? CUSTOM : d.strategy_id,
    };
    const start = ui().rule_templates.find((t) => t.name === ui().initial_rule_set) ?? ui().rule_templates[0];
    this.builder = new RuleBuilder(builder, structuredClone(start), (rules) => { this.state.rules = rules; this.emit(); });
    this.render();
  }

  private readonly builder: RuleBuilder;
  private get isCustom() { return this.state.strategy_id === CUSTOM; }

  get request(): BacktestRequest { return this.payload(); }

  private payload(): BacktestRequest {
    return this.isCustom ? { ...this.state, strategy_id: "custom", params: {}, rules: this.builder.rules } : { ...this.state, rules: undefined, params: { ...this.state.params } };
  }

  private get strategy(): StrategyInfo { return this.catalog.strategies.find((s) => s.id === this.state.strategy_id)!; }

  private set<K extends keyof BacktestRequest>(key: K, value: BacktestRequest[K]) {
    this.state[key] = value;
    this.emit();
  }

  private render() {
    const L = ui().limits;
    this.el.replaceChildren(
      h("h2", {}, "Strategy"),
      field("Instrument", select(this.symbols.map((s) => ({ value: s.symbol, label: `${s.symbol} · ${s.rows.toLocaleString()} days` })), this.state.symbol, (v) => this.set("symbol", v))),
      field("Rule", select([...this.catalog.strategies.map((s) => ({ value: s.id, label: s.name })), { value: CUSTOM, label: "Build your own..." }], this.state.strategy_id, (v) => {
        this.state.strategy_id = v;
        if (v !== CUSTOM) this.state.params = defaults(this.strategy);
        this.render();
        this.emit();
      })),
      this.isCustom ? this.builder.el : h("p", { class: "hint" }, this.strategy.description),
      ...(this.isCustom ? [] : this.strategy.params).map((p) => field(p.label, p.kind === "select"
        ? select(p.options!, String(this.state.params[p.key]), (v) => this.setParam(p.key, v))
        : numberInput(Number(this.state.params[p.key]), p, (v) => this.setParam(p.key, v)))),
      h("h2", { class: "spaced" }, "Money & limits"),
      field(`Starting capital (${ui().currency.symbol})`, numberInput(this.state.initial_capital, L.initial_capital, (v) => this.set("initial_capital", v))),
      h("p", { class: "hint tight" }, "Use 0 to see how much money the strategy needs: the dashboard tracks your lowest and highest cash balance."),
      ...(this.isCustom ? [] : [field("Lots per position", numberInput(this.state.lots, L.lots, (v) => this.set("lots", Math.round(v))))]),
      field("Max lots held (0 = no limit)", numberInput(this.state.max_position, L.max_position, (v) => this.set("max_position", Math.round(v)))),
      toggle("Allow selling before buying", "A sell with nothing to sell opens a short position. When off, sells only close what you hold.", this.state.allow_short, (v) => this.set("allow_short", v)),
      toggle("Apply charges", "Charge a % of the traded value on every buy and sell.", this.state.charges_enabled, (v) => { this.state.charges_enabled = v; this.render(); this.emit(); }),
      ...(this.state.charges_enabled ? [field("Charge per trade (%)", numberInput(this.state.fee_pct, L.fee_pct, (v) => this.set("fee_pct", v)))] : []),
      h("h2", { class: "spaced" }, "Period"),
      this.periodChips(),
      ...(this.custom ? [h("div", { class: "row2" },
        field("From", dateInput((v) => this.setRange("start", v))), field("To", dateInput((v) => this.setRange("end", v))))] : []),
    );
  }

  private setParam(key: string, value: number | string) {
    this.state.params = { ...this.state.params, [key]: value } as ParamValues;
    this.emit();
  }

  private setRange(key: "start" | "end", value: string) {
    this.state[key] = value || undefined;
    this.state.period = undefined;
    this.emit();
  }

  private periodChips(): HTMLElement {
    const chip = (label: string, active: boolean, click: () => void) =>
      h("button", { type: "button", class: `chip${active ? " active" : ""}`, on: { click } }, label);
    return h("div", { class: "chips" },
      ...this.catalog.periods.map((p) => chip(p, !this.custom && this.state.period === p, () => {
        this.custom = false; this.state.period = p; this.state.start = this.state.end = undefined;
        this.render(); this.emit();
      })),
      chip("Custom", this.custom, () => { this.custom = true; this.render(); }));
  }
}

const defaults = (s: StrategyInfo): ParamValues => Object.fromEntries(s.params.map((p) => [p.key, p.default]));

const field = (label: string, input: HTMLElement) => h("label", { class: "field" }, h("span", {}, label), input);

function select(options: { value: string; label: string }[], value: string, on: (v: string) => void) {
  return h("select", { on: { change: (e) => on((e.target as HTMLSelectElement).value) } },
    options.map((o) => h("option", { value: o.value, selected: o.value === value }, o.label)));
}

function numberInput(value: number, range: { min?: number; max?: number; step?: number }, on: (v: number) => void) {
  return h("input", {
    type: "number", value: String(value), min: range.min, max: range.max, step: range.step ?? "any",
    on: { input: (e) => { const v = (e.target as HTMLInputElement).valueAsNumber; if (!Number.isNaN(v)) on(v); } },
  });
}

const dateInput = (on: (v: string) => void) => h("input", { type: "date", on: { change: (e) => on((e.target as HTMLInputElement).value) } });

function toggle(label: string, help: string, value: boolean, on: (v: boolean) => void) {
  return h("label", { class: "toggle" },
    h("input", { type: "checkbox", checked: value, on: { change: (e) => on((e.target as HTMLInputElement).checked) } }),
    h("span", { class: "track" }), h("span", { class: "toggle-text" }, h("strong", {}, label), h("small", {}, help)));
}
