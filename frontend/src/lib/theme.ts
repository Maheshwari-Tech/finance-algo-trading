import { Chart, registerables } from "chart.js";

Chart.register(...registerables);

export const color = {
  accent: "#7c8cff", accent2: "#37d6c5", up: "#34d399", down: "#fb7185", warn: "#fbbf24",
  muted: "#8b93a7", grid: "rgba(255,255,255,0.06)", text: "#c9d0e3",
};

Chart.defaults.color = color.muted;
Chart.defaults.font.family = "Inter, system-ui, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.borderColor = color.grid;
Chart.defaults.animation = { duration: 450 };
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.tooltip.backgroundColor = "rgba(14,17,28,0.95)";
Chart.defaults.plugins.tooltip.borderColor = "rgba(255,255,255,0.1)";
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.titleColor = "#fff";

export function gradient(canvas: HTMLCanvasElement, rgb: string, top = 0.35): CanvasGradient {
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 0, canvas.height || 300);
  g.addColorStop(0, `rgba(${rgb},${top})`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  return g;
}
