/* Only the ECharts pieces the catalog uses, loaded lazily with the first chart. */
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart, LineChart, PieChart, SankeyChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, LineChart, PieChart, ScatterChart, HeatmapChart, SankeyChart, GridComponent, LegendComponent,
  TooltipComponent, VisualMapComponent, CanvasRenderer]);

export default echarts;
