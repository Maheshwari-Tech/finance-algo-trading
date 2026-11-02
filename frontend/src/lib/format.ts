import { ui } from "./uiConfig";

export const pct = (v: number, digits = 1, signed = false) =>
  `${signed && v > 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;

export const money = (v: number, signed = false) => {
  const { symbol, locale } = ui().currency;
  const s = Math.abs(v).toLocaleString(locale, { maximumFractionDigits: 0 });
  return `${v < 0 ? "-" : signed && v > 0 ? "+" : ""}${symbol}${s}`;
};

export const num = (v: number, digits = 2) => v.toFixed(digits);

export const plural = (n: number, unit: string) => `${n.toLocaleString()} ${unit}${n === 1 ? "" : "s"}`;

export const tone = (v: number): "up" | "down" | "flat" => (v > 0 ? "up" : v < 0 ? "down" : "flat");

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
