"use client";

import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { LossPoint } from "@/types/api";

interface LossChartProps {
  data: LossPoint[];
  height?: number;
}

export function LossChart({ data, height = 180 }: LossChartProps) {
  const chartData = useMemo(() => data.map((d) => ({ step: d.step, loss: d.loss })), [data]);

  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center rounded border border-dashed text-xs text-muted-foreground"
        style={{ height }}
      >
        等待训练数据...
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="var(--border)"
          opacity={0.4}
        />
        <XAxis
          dataKey="step"
          tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
          axisLine={{ stroke: "var(--border)" }}
          tickLine={false}
          label={{ value: "Step", position: "insideBottomRight", offset: -4, fontSize: 10, fill: "var(--muted-foreground)" }}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
          axisLine={false}
          tickLine={false}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--popover)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            fontSize: "12px",
            color: "var(--popover-foreground)",
          }}
          labelStyle={{ color: "var(--muted-foreground)" }}
          formatter={(value: any) => [Number(value).toFixed(4), "Loss"]}
          labelFormatter={(label: any) => `Step ${label}`}
        />
        <Line
          type="monotone"
          dataKey="loss"
          stroke="var(--chart-1)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 3, stroke: "var(--chart-1)", strokeWidth: 2, fill: "var(--background)" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
