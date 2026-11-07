import { api, ApiError } from "../api/client";
import type { FeedbackItem, SymbolInfo, UploadSpec } from "../api/types";
import { priceViewer } from "../components/priceViewer";
import { h } from "../lib/dom";

export async function adminPage(root: HTMLElement): Promise<void> {
  const body = h("div");
  root.append(body);

  let viewing: string | null = null;
  const viewerSlot = h("div");

  function view(symbol: string | null) {
    viewing = symbol;
    viewerSlot.replaceChildren(...(symbol ? [priceViewer(symbol)] : []));
    if (symbol) viewerSlot.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function render(notice?: HTMLElement) {
    const [symbols, spec, feedback] = await Promise.all([api.symbols(), api.uploadSpec(), api.feedback()]);
    if (viewing && !symbols.some((s) => s.symbol === viewing)) viewing = null;
    body.replaceChildren(manager(symbols, spec, notice), viewerSlot, feedbackList(feedback));
    view(viewing);
  }

  function feedbackList(items: FeedbackItem[]): HTMLElement {
    const when = (iso: string) => new Date(iso).toLocaleString();
    const shot = (f: FeedbackItem) => {
      if (!f.has_screenshot) return "-";
      const holder = h("div", { class: "shot-cell" }, h("button", { class: "btn ghost", on: { click: async () => {
        const url = await api.feedbackScreenshot(f.id);
        holder.replaceChildren(h("a", { href: url, target: "_blank", rel: "noopener" }, h("img", { src: url, alt: `Screenshot for feedback #${f.id}` })));
      } } }, "View screenshot"));
      return holder;
    };
    return h("section", { class: "panel feedback-admin" },
      h("div", { class: "panel-head" }, h("h2", {}, "Feedback"), h("span", { class: "sub" }, `${items.length} message${items.length === 1 ? "" : "s"}, newest first`)),
      items.length === 0 ? h("p", { class: "hint" }, "No feedback yet.") : h("div", { class: "table-scroll tall" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ["#", "When", "From", "Type", "Message", "Screenshot"].map((c) => h("th", {}, c)))),
        h("tbody", {}, items.map((f) => h("tr", {},
          h("td", {}, String(f.id)), h("td", {}, when(f.created_at)), h("td", {}, f.mobile),
          h("td", {}, f.category ? h("span", { class: "tag long" }, f.category) : "-"),
          h("td", { class: "feedback-msg" }, f.message ?? "-"), h("td", {}, shot(f))))))));
  }

  function manager(symbols: SymbolInfo[], spec: UploadSpec, notice?: HTMLElement): HTMLElement {
    const symbol = h("input", { placeholder: "Symbol", maxLength: 20 });
    const file = h("input", { type: "file", accept: ".csv,text/csv" });
    const mode = h("select", {}, h("option", { value: "replace" }, "Replace existing data"), h("option", { value: "merge" }, "Merge by date (update + append)"));
    const msg = notice ?? h("div", { class: "msg" });
    const setMsg = (text: string, isError: boolean) => { msg.textContent = text; msg.className = `msg ${isError ? "error" : "ok"}`; };

    const upload = async (e: Event) => {
      e.preventDefault();
      if (!file.files?.[0]) { setMsg("Choose a CSV file first", true); return; }
      try {
        const info = await api.upload(symbol.value, mode.value, file.files[0]);
        const done = h("div", {});
        done.textContent = `Saved ${info.symbol}: ${info.rows.toLocaleString()} rows (${info.start} → ${info.end})`;
        done.className = "msg ok";
        viewing = info.symbol;
        await render(done);
      } catch (err) {
        setMsg(err instanceof ApiError ? [err.message, ...err.problems].join("\n• ") : "Upload failed", true);
      }
    };

    const remove = async (s: SymbolInfo) => {
      if (!confirm(`Delete ${s.symbol} and all ${s.rows.toLocaleString()} of its rows?`)) return;
      await api.remove(s.symbol);
      await render();
    };

    return h("div", { class: "admin-grid" },
      h("form", { class: "panel", on: { submit: upload } },
        h("h2", {}, "Upload price data"),
        h("p", { class: "hint" }, "CSV with columns ", h("code", {}, spec.columns.join(", ")), `. At least ${spec.min_rows} rows, up to ${spec.max_upload_mb} MB. One row per trading day.`),
        h("label", { class: "field" }, h("span", {}, "Instrument symbol"), symbol),
        h("label", { class: "field" }, h("span", {}, "If it already exists"), mode),
        h("label", { class: "field" }, h("span", {}, "CSV file"), file),
        msg, h("button", { class: "btn primary", type: "submit" }, "Upload"),
        h("button", { class: "btn ghost block", type: "button", on: { click: () => void api.downloadTemplate() } }, "Download CSV template")),
      h("section", { class: "panel" },
        h("div", { class: "panel-head" }, h("h2", {}, "Datasets"), h("span", { class: "sub" }, `${symbols.length} instrument${symbols.length === 1 ? "" : "s"}`)),
        symbols.length === 0 ? h("p", { class: "hint" }, "Nothing uploaded yet.") : h("table", { class: "data" },
          h("thead", {}, h("tr", {}, ["Symbol", "Rows", "From", "To", ""].map((c) => h("th", {}, c)))),
          h("tbody", {}, symbols.map((s) => h("tr", {}, h("td", {}, h("strong", {}, s.symbol)), h("td", {}, s.rows.toLocaleString()), h("td", {}, s.start), h("td", {}, s.end),
            h("td", {}, h("button", { class: "btn ghost", on: { click: () => view(s.symbol) } }, "View"),
              h("button", { class: "btn danger", on: { click: () => void remove(s) } }, "Delete"))))))));
  }

  await render();
}
