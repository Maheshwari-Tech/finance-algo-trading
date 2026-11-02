import { Chart, type ChartConfiguration } from "chart.js";
import type { BacktestResult } from "../api/types";
import { h } from "../lib/dom";

/** A dashboard tile. Add a new analysis by writing a ChartPanel and listing it in charts/index.ts. */
export interface ChartPanel {
  id: string;
  title: string;
  subtitle?: string;
  wide?: boolean;
  /** Renders into `host`; returns an optional cleanup function. */
  render(host: HTMLElement, result: BacktestResult): void | (() => void);
}

export function canvasChart(host: HTMLElement, build: (canvas: HTMLCanvasElement) => ChartConfiguration): () => void {
  const canvas = h("canvas");
  host.append(h("div", { class: "chart-box" }, canvas));
  const chart = new Chart(canvas, build(canvas));
  return () => chart.destroy();
}

export const dateAxis = { ticks: { maxTicksLimit: 7, maxRotation: 0 }, grid: { display: false } };
