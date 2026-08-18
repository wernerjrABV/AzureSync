import { useState } from "react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { AppShell } from "@astryxdesign/core/AppShell";
import { TopNav } from "@astryxdesign/core/TopNav";
import { TopNavHeading } from "@astryxdesign/core/TopNav";
import { SideNav } from "@astryxdesign/core/SideNav";
import { SideNavItem } from "@astryxdesign/core/SideNav";
import { Banner } from "@astryxdesign/core/Banner";
import WorkItemsListPage from "./pages/WorkItemsListPage";
import FeaturesRoadmapPage from "./pages/FeaturesRoadmapPage";
import SynchronizationPage from "./pages/SynchronizationPage";
import CapacityFlowPage from "./pages/CapacityFlowPage";

const INFO_MESSAGE = "";

type Page = "work-items" | "features-roadmap" | "synchronization" | "capacity-flow";

export default function App() {
  const [page, setPage] = useState<Page>("work-items");

  return (
    <Theme theme={neutralTheme}>
      <AppShell
        variant="elevated"
        contentPadding={4}
        topNav={
          <TopNav
            label="Main navigation"
            heading={<TopNavHeading heading="Engineering Portfolio" />}
          />
        }
        sideNav={
          <SideNav collapsible={{defaultIsCollapsed: true}}>
            <SideNavItem
              label="Work Items"
              icon="viewColumns"
              isSelected={page === "work-items"}
              onClick={() => setPage("work-items")}
            />
            <SideNavItem
              label="Features Roadmap"
              icon="calendar"
              isSelected={page === "features-roadmap"}
              onClick={() => setPage("features-roadmap")}
            />
            <SideNavItem
              label="Synchronization"
              icon="wrench"
              isSelected={page === "synchronization"}
              onClick={() => setPage("synchronization")}
            />
          </SideNav>
        }
        banner={
          INFO_MESSAGE ? <Banner status="info" title={INFO_MESSAGE} /> : undefined
        }
      >
        {page === "work-items" ? (
          <WorkItemsListPage />
        ) : page === "features-roadmap" ? (
          <FeaturesRoadmapPage />
        ) : page === "synchronization" ? (
          <SynchronizationPage />
        ) : (
          <CapacityFlowPage />
        )}
      </AppShell>
    </Theme>
  );
}
