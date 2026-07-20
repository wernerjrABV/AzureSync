import { useCallback, useMemo, useState } from "react";
import { Gantt, Willow } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./GanttChart.css";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Text } from "@astryxdesign/core/Text";
import { HStack } from "@astryxdesign/core/Layout";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack } from "@astryxdesign/core/Layout";
import { buildGanttTasks, type GanttTask } from "../utils/buildGanttTasks";
import type { FeatureTreeNode } from "../utils/buildFeatureTree";
import type { IColumnConfig, ITask } from "@svar-ui/react-gantt";

function formatColumnDate(date: Date | null): string {
  return date === null ? "—" : date.toISOString().slice(0, 10);
}

function formatColumnDurationDays(start: Date | null, end: Date | null): string {
  if (start === null || end === null) return "—";
  const days = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
  return `${days} day(s)`;
}

const GRID_COLUMNS: IColumnConfig[] = [
  { id: "text", header: "Task name", width: 460, flexgrow: 3 },
];

const GANTT_SCALES = [{ unit: "month" as const, step: 1, format: "%m/%Y" }];

type GanttVariant = "success" | "neutral" | "info" | "error" | "warning";

const VARIANT_COLORS: Record<GanttVariant, string> = {
  info: "#1e40af",
  success: "var(--color-text-green)",
  error: "var(--color-text-red)",
  neutral: "#52525b",
  warning: "#a16207",
};

const LEGEND_COLOR_ITEMS: Array<{ variant: GanttVariant; label: string }> = [
  { variant: "neutral", label: "New" },
  { variant: "info", label: "In progress / other" },
  { variant: "success", label: "Closed" },
  { variant: "error", label: "Overdue (still open)" },
  { variant: "warning", label: "Closed late" },
];

function GanttLegend() {
  return (
    <HStack gap={4} align="center" wrap="wrap">
      {LEGEND_COLOR_ITEMS.map(({ variant, label }) => (
        <HStack key={variant} gap={2} align="center">
          <span
            className="gantt-legend-swatch"
            style={{ backgroundColor: VARIANT_COLORS[variant] }}
          />
          <Text type="supporting">
            {label}
          </Text>
        </HStack>
      ))}
      <HStack gap={2} align="center">
        <span className="gantt-legend-swatch gantt-legend-swatch--solid" />
        <Text type="supporting">
          Executed period (solid)
        </Text>
      </HStack>
      <HStack gap={2} align="center">
        <span className="gantt-legend-swatch gantt-legend-swatch--planned" />
        <Text type="supporting">Planned period (hatched)</Text>
      </HStack>
      <HStack gap={2} align="center">
        <span className="gantt-legend-marker" />
        <Text type="supporting">
          Start / target date marker
        </Text>
      </HStack>
    </HStack>
  );
}

// Gantt bar coloring: green for Closed, gray for New, blue for anything
// else — overridden by lateness: red when still open past its target
// date, darker yellow when it closed after its target date.
function taskVariant(data: ITask): GanttVariant {
  const state = data.state as string | null;
  const plannedEnd = data.plannedEnd as Date | null;
  const executedEnd = data.executedEnd as Date | null;
  const isClosed = state === "Closed";

  if (!isClosed && plannedEnd !== null && new Date() > plannedEnd) {
    return "error";
  }
  if (isClosed && plannedEnd !== null && executedEnd !== null && executedEnd > plannedEnd) {
    return "warning";
  }
  if (isClosed) {
    return "success";
  }
  if (state === "New") {
    return "neutral";
  }
  return "info";
}

function percentWithin(date: Date, start: Date, end: Date): number {
  const total = end.getTime() - start.getTime();
  if (total <= 0) return 0;
  return ((date.getTime() - start.getTime()) / total) * 100;
}

function GanttBarContent({ data }: { data: ITask }) {
  const variant = taskVariant(data);
  const start = data.start as Date;
  const end = data.end as Date;
  const plannedStart = data.plannedStart as Date | null;
  const plannedEnd = data.plannedEnd as Date | null;
  const executedStart = data.executedStart as Date | null;
  const executedEnd = data.executedEnd as Date | null;

  return (
    <>
      {/* Full-box solid fill in the state color. This spans the whole bar
         (the union of the planned and executed ranges) so the base SVAR
         bar — near-white in dark mode — never shows through, keeping every
         visible color one from the legend. */}
      {plannedStart !== null && plannedEnd !== null && (
        <div
          className={`gantt-bar-fill gantt-bar-fill--planned gantt-bar-fill--${variant}`}
          style={{
            left: `${percentWithin(plannedStart, start, end)}%`,
            right: `${100 - percentWithin(plannedEnd, start, end)}%`,
          }}
        />
      )}
      {executedStart !== null && executedEnd !== null && (
        <div
          className={`gantt-bar-fill gantt-bar-fill--executed gantt-bar-fill--${variant}`}
          style={{
            left: `${percentWithin(executedStart, start, end)}%`,
            right: `${100 - percentWithin(executedEnd, start, end)}%`,
          }}
        />
      )}
      {/* Planned start/target markers, drawn above everything. */}
      {plannedStart !== null && (
        <div className="gantt-bar-marker" style={{ left: `${percentWithin(plannedStart, start, end)}%` }} />
      )}
      {plannedEnd !== null && (
        <div className="gantt-bar-marker" style={{ left: `${percentWithin(plannedEnd, start, end)}%` }} />
      )}
    </>
  );
}

export interface GanttChartProps {
  roots: FeatureTreeNode[];
}

// One month before the earliest date and one month after the latest, so
// the chart doesn't waste width on empty scale before/after the data.
function computeChartRange(tasks: GanttTask[]): { start: Date; end: Date } {
  const starts = tasks.map((t) => t.start.getTime());
  const ends = tasks.map((t) => t.end.getTime());
  const earliest = new Date(Math.min(...starts));
  const latest = new Date(Math.max(...ends));
  return {
    start: new Date(earliest.getFullYear(), earliest.getMonth() - 1, 1),
    end: new Date(latest.getFullYear(), latest.getMonth() + 2, 0),
  };
}

export default function GanttChart({ roots }: GanttChartProps) {
  const [selectedTask, setSelectedTask] = useState<ITask | null>(null);
  const tasks = useMemo(() => buildGanttTasks(roots), [roots]);
  const handleTaskSelect = useCallback(
    (event: { id?: number | string }) => {
      const task = tasks.find((candidate) => String(candidate.id) === String(event?.id));
      setSelectedTask(task ?? null);
    },
    [tasks],
  );

  const chartRange = useMemo(
    () => (tasks.length > 0 ? computeChartRange(tasks) : null),
    [tasks],
  );

  const gantt = useMemo(
    () => chartRange === null ? null : (
      <Willow>
        <Gantt
          readonly={true}
          tasks={tasks}
          start={chartRange.start}
          end={chartRange.end}
          cellWidth={60}
          gridWidth={480}
          columns={GRID_COLUMNS}
          onSelectTask={handleTaskSelect}
          scales={GANTT_SCALES}
          taskTemplate={GanttBarContent}
        />
      </Willow>
    ),
    [chartRange, handleTaskSelect, tasks],
  );

  if (chartRange === null) {
    return (
      <EmptyState
        title="No items with dates to plot"
        description="The Gantt chart needs at least one Solution, Epic, or Feature with both a start and target date."
      />
    );
  }

  return (
    <>
      {gantt}
      <GanttLegend />
      <Dialog
        isOpen={selectedTask !== null}
        onOpenChange={(isOpen) => !isOpen && setSelectedTask(null)}
        width={630}
        maxHeight="100vh"
        position={{ top: 0, right: 0, bottom: 0 }}
        className="roadmap-details-drawer"
      >
        {selectedTask && (
          <>
            <DialogHeader
              title="Task details"
              onOpenChange={(isOpen) => !isOpen && setSelectedTask(null)}
            />
            <VStack gap={3}>
              <Text>ID: {String(selectedTask.id)}</Text>
              <Text>Title: {String(selectedTask.text).replace(/^#\d+\s*/, "")}</Text>
              <Text>State: {String(selectedTask.state ?? "—")}</Text>
              <Text>Planned start: {formatColumnDate(selectedTask.plannedStart as Date | null)}</Text>
              <Text>Planned target: {formatColumnDate(selectedTask.plannedEnd as Date | null)}</Text>
              <Text>Executed start: {formatColumnDate(selectedTask.executedStart as Date | null)}</Text>
              <Text>Executed end: {formatColumnDate(selectedTask.executedEnd as Date | null)}</Text>
              <Text as="div">
                Description:{" "}
                {selectedTask.description ? (
                  <span
                    className="roadmap-description"
                    dangerouslySetInnerHTML={{ __html: selectedTask.description }}
                  />
                ) : "—"}
              </Text>
            </VStack>
          </>
        )}
      </Dialog>
    </>
  );
}
