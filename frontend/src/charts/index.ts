import { capitalPanel, drawdownPanel, equityPanel, histogramPanel, positionPanel, pricePanel, tradesPanel } from "./core";
import { feesPanel, monthlyPanel, windowsPanel } from "./analysis";
import type { ChartPanel } from "./panel";

/** Order here is the order on the dashboard. */
export const PANELS: ChartPanel[] = [capitalPanel, equityPanel, pricePanel, positionPanel, drawdownPanel, windowsPanel, feesPanel, monthlyPanel, tradesPanel, histogramPanel];
