import { api, ApiError } from "../api/client";
import { h } from "../lib/dom";

const CATEGORIES = ["Bug", "Idea", "Other"];
const MAX_MB = 5;

/** Everything is optional: a message, a category, a screenshot. We save what is given. */
export async function feedbackPage(root: HTMLElement): Promise<void> {
  const message = h("textarea", { rows: 7, maxLength: 5000, placeholder: "What works, what doesn't, what you'd like to see..." });
  let category = "";
  const chips = h("div", { class: "chips" });
  const drawChips = () => chips.replaceChildren(...CATEGORIES.map((c) => h("button", {
    type: "button", class: `chip${category === c ? " active" : ""}`, on: { click: () => { category = category === c ? "" : c; drawChips(); } },
  }, c)));
  drawChips();
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp" });
  const preview = h("div", { class: "shot-preview" });
  file.addEventListener("change", () => {
    const f = file.files?.[0];
    preview.replaceChildren(...(f ? [h("img", { src: URL.createObjectURL(f), alt: "Screenshot preview" }),
      h("button", { type: "button", class: "btn ghost", on: { click: () => { file.value = ""; preview.replaceChildren(); } } }, "Remove")] : []));
  });
  const msg = h("p", { class: "msg" });
  const say = (text: string, kind: "ok" | "error") => { msg.textContent = text; msg.className = `msg ${kind}`; };
  const button = h("button", { class: "btn primary", type: "submit" }, "Send feedback");

  const submit = async (e: Event) => {
    e.preventDefault();
    const shot = file.files?.[0] ?? null;
    if (!message.value.trim() && !shot) { say("Write a message or attach a screenshot.", "error"); return; }
    if (shot && shot.size > MAX_MB * 1024 * 1024) { say(`Screenshot is larger than ${MAX_MB} MB.`, "error"); return; }
    button.disabled = true;
    try {
      await api.sendFeedback(message.value, category, shot);
      message.value = ""; category = ""; drawChips(); file.value = ""; preview.replaceChildren();
      say("Thank you, your feedback was saved.", "ok");
    } catch (err) {
      say(err instanceof ApiError ? err.message : "Could not send feedback", "error");
    } finally {
      button.disabled = false;
    }
  };

  root.append(h("div", { class: "feedback-wrap" }, h("form", { class: "panel feedback", on: { submit } },
    h("h2", {}, "Feedback"),
    h("p", { class: "hint" }, "Everything here is optional. Tell us anything, pick a type if you like, attach a screenshot if it helps."),
    h("label", { class: "field" }, h("span", {}, "Message"), message),
    h("div", { class: "field" }, h("span", {}, "Type (optional)"), chips),
    h("label", { class: "field" }, h("span", {}, `Screenshot (optional, PNG/JPEG/GIF/WebP up to ${MAX_MB} MB)`), file),
    preview, msg, button)));
}
