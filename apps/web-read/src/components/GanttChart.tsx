import { Gantt, Willow } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./GanttChart.css";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Text } from "@astryxdesign/core/Text";
import { buildGanttTasks } from "../utils/buildGanttTasks";
import { stateToBadgeVariant, type FeatureTreeNode } from "../utils/buildFeatureTree";
import type { ITask } from "@svar-ui/react-gantt";

function countAllNodes(roots: FeatureTreeNode[]): number {
  let count = 0;
  const stack = [...roots];
  while (stack.length > 0) {
    const n = stack.pop()!;
    count += 1;
    stack.push(...n.children);
  }
  return count;
}

function GanttBarContent({ data }: { data: ITask }) {
  const variant = stateToBadgeVariant(data.state as string | null);
  return <div className={`gantt-bar-fill gantt-bar-fill--${variant}`} />;
}

export interface GanttChartProps {
  roots: FeatureTreeNode[];
}

export default function GanttChart({ roots }: GanttChartProps) {
  const tasks = buildGanttTasks(roots);
  const omittedCount = countAllNodes(roots) - tasks.length;

  if (tasks.length === 0) {
    return (
      <EmptyState
        title="No items with dates to plot"
        description="The Gantt chart needs at least one Solution, Epic, or Feature with both a start and target date."
      />
    );
  }

  return (
    <>
      {omittedCount > 0 && (
        <Text>
          {omittedCount} item(s) hidden from the Gantt chart for missing start or target date.
        </Text>
      )}
      <Willow>
        <Gantt
          readonly={true}
          tasks={tasks}
          scales={[{ unit: "month", step: 1, format: "%F %Y" }]}
          taskTemplate={GanttBarContent}
        />
      </Willow>
    </>
  );
}
