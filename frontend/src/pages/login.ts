import { api, ApiError } from "../api/client";
import type { AuthConfig, UserInfo } from "../api/types";
import { clear, h } from "../lib/dom";
import { session } from "../lib/session";

export async function loginPage(root: HTMLElement, onLoggedIn: (user: UserInfo) => void): Promise<void> {
  const cfg: AuthConfig = await api.authConfig();
  const card = h("div", { class: "panel login" });
  root.append(h("div", { class: "login-wrap" }, card));

  let timer: number | undefined;

  const message = (el: HTMLElement, text: string, kind: "error" | "ok" = "error") => { el.textContent = text; el.className = `msg ${kind}`; };

  function mobileStep(initial = "") {
    window.clearInterval(timer);
    const input = h("input", { type: "tel", inputMode: "numeric", autocomplete: "tel-national", placeholder: "Mobile number", value: initial, autofocus: true });
    const msg = h("p", { class: "msg" });
    const button = h("button", { class: "btn primary", type: "submit" }, "Send code");
    const submit = async (e: Event) => {
      e.preventDefault();
      button.disabled = true;
      try {
        const { cooldown_seconds } = await api.requestOtp(input.value);
        otpStep(input.value, cooldown_seconds);
      } catch (err) {
        message(msg, err instanceof ApiError ? err.message : "Could not send the code");
        button.disabled = false;
      }
    };
    clear(card);
    card.append(h("form", { on: { submit } },
      h("h2", {}, "Sign in"), h("p", { class: "hint" }, "Enter your mobile number. We will send you a one-time code."),
      h("label", { class: "field" }, h("span", {}, "Mobile number"), h("div", { class: "phone" }, h("span", { class: "cc" }, `+${cfg.country_code}`), input)),
      msg, button));
  }

  function otpStep(mobile: string, cooldown: number) {
    const input = h("input", { inputMode: "numeric", autocomplete: "one-time-code", maxLength: cfg.otp_length, placeholder: "•".repeat(cfg.otp_length), class: "otp", autofocus: true });
    const msg = h("p", { class: "msg" });
    const resend = h("button", { type: "button", class: "btn ghost", disabled: true });
    const button = h("button", { class: "btn primary", type: "submit" }, "Verify & continue");

    let left = cooldown;
    const tick = () => {
      resend.textContent = left > 0 ? `Resend code in ${left}s` : "Resend code";
      resend.disabled = left > 0;
      if (left-- <= 0) window.clearInterval(timer);
    };
    window.clearInterval(timer);
    timer = window.setInterval(tick, 1000);
    tick();

    resend.addEventListener("click", async () => {
      try { left = (await api.requestOtp(mobile)).cooldown_seconds; message(msg, "A new code was sent", "ok"); timer = window.setInterval(tick, 1000); tick(); }
      catch (err) { message(msg, err instanceof ApiError ? err.message : "Could not resend"); }
    });

    const submit = async (e: Event) => {
      e.preventDefault();
      button.disabled = true;
      try {
        const login = await api.verifyOtp(mobile, input.value.trim());
        session.set(login.token);
        window.clearInterval(timer);
        onLoggedIn({ mobile: login.mobile, role: login.role });
      } catch (err) {
        message(msg, err instanceof ApiError ? err.message : "Verification failed");
        button.disabled = false;
      }
    };
    clear(card);
    card.append(h("form", { on: { submit } },
      h("h2", {}, "Enter code"),
      h("p", { class: "hint" }, `Enter the OTP or access code given to you for ${mobile}.`),
      h("label", { class: "field" }, h("span", {}, "OTP or access code"), input), msg, button,
      h("div", { class: "login-links" }, resend, h("button", { type: "button", class: "btn ghost", on: { click: () => mobileStep() } }, "Change number"))));
  }

  mobileStep();
}
