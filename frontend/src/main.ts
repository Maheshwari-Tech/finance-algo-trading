import "./styles/main.css";
import "./lib/theme";
import { api } from "./api/client";
import type { UserInfo } from "./api/types";
import { clear, h } from "./lib/dom";
import { AUTH_EXPIRED, session } from "./lib/session";
import { setUiConfig } from "./lib/uiConfig";
import { clearSavedCache, loadSaved } from "./lib/savedStrategies";
import { adminPage } from "./pages/admin";
import { comparePage } from "./pages/compare";
import { dashboardPage } from "./pages/dashboard";
import { feedbackPage } from "./pages/feedback";
import { loginPage } from "./pages/login";
import { testRulePage } from "./pages/testRule";

const app = document.getElementById("app")!;
const main = h("main", { class: "page" });
let user: UserInfo | null = null;

const routes: Record<string, { admin?: boolean; page: (root: HTMLElement) => Promise<void> }> = {
  "/": { page: dashboardPage },
  "/test": { page: testRulePage },
  "/compare": { page: comparePage },
  "/feedback": { page: feedbackPage },
  "/admin": { admin: true, page: adminPage },
};

function topbar(): HTMLElement {
  const path = location.hash.slice(1) || "/";
  const link = (to: string, label: string) => h("a", { href: `#${to}`, class: path === to ? "active" : "" }, label);
  return h("header", { class: "topbar" },
    h("div", { class: "brand" }, h("span", { class: "logo" }), h("strong", {}, "Strategic Trader"), h("span", { class: "tagline" }, "Try a trading idea on real history")),
    h("nav", {}, link("/test", "Test a rule"), link("/", "Strategy"), link("/compare", "Compare"), link("/feedback", "Feedback"), user?.role === "admin" && link("/admin", "Admin"),
      h("span", { class: "who" }, user!.mobile),
      h("button", { class: "btn ghost", on: { click: () => void signOut() } }, "Sign out")));
}

async function signOut() {
  try { await api.logout(); } catch { /* token may already be invalid */ }
  session.clear();
  clearSavedCache();
  await boot();
}

async function renderPage() {
  clear(app);
  clear(main);
  app.append(topbar(), main);
  const route = routes[location.hash.slice(1) || "/"] ?? routes["/"];
  if (route.admin && user?.role !== "admin") { location.hash = "/"; return; }
  try { await route.page(main); } catch { main.append(h("div", { class: "panel error" }, "Could not reach the server.")); }
}

async function boot() {
  clear(app);
  user = null;
  if (session.token()) {
    try { user = await api.me(); } catch { session.clear(); }
  }
  if (!user) {
    const shell = h("div");
    app.append(shell);
    try { await loginPage(shell, () => void boot()); } catch { shell.append(h("div", { class: "panel error" }, "Could not reach the server.")); }
    return;
  }
  setUiConfig(await api.uiConfig());
  await loadSaved(true);
  await renderPage();
}

window.addEventListener("hashchange", () => { if (user) void renderPage(); });
window.addEventListener(AUTH_EXPIRED, () => { session.clear(); void boot(); });
void boot();
