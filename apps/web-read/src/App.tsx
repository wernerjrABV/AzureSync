import { AppShell } from "@astryxdesign/core/AppShell";
import { TopNav } from "@astryxdesign/core/TopNav";
import { TopNavHeading } from "@astryxdesign/core/TopNav";
import WorkItemsListPage from "./pages/WorkItemsListPage";

export default function App() {
  return (
    <AppShell
      variant="elevated"
      contentPadding={4}
      topNav={
        <TopNav
          label="Main navigation"
          heading={<TopNavHeading heading="Work Items" />}
        />
      }
    >
      <WorkItemsListPage />
    </AppShell>
  );
}
