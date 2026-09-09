import { useEffect, useState } from "react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { AppShell } from "@astryxdesign/core/AppShell";
import { TopNav } from "@astryxdesign/core/TopNav";
import { TopNavHeading } from "@astryxdesign/core/TopNav";
import { SideNav } from "@astryxdesign/core/SideNav";
import { SideNavItem } from "@astryxdesign/core/SideNav";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { fetchUpdateStatus, startUpdate } from "./services/syncServiceClient";
import type { UpdateStatus } from "./services/syncServiceClient";
import WorkItemsListPage from "./pages/WorkItemsListPage";
import FeaturesRoadmapPage from "./pages/FeaturesRoadmapPage";
import SynchronizationPage from "./pages/SynchronizationPage";
import CapacityFlowPage from "./pages/CapacityFlowPage";

const INFO_MESSAGE = "";
const APP_VERSION = "0.2.0";

type Page = "work-items" | "features-roadmap" | "synchronization" | "capacity-flow";

export default function App() {
  const [page, setPage] = useState<Page>("work-items");
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    let active = true;
    fetchUpdateStatus().then((status) => {
      if (active && status.update_available) setUpdate(status);
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  const handleUpdate = async () => {
    setIsUpdating(true);
    try {
      await startUpdate();
      setUpdate(null);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <Theme theme={neutralTheme}>
      <AppShell
        variant="elevated"
        contentPadding={4}
        topNav={
          <TopNav
            label="Main navigation"
            heading={
              <TopNavHeading
                heading="Engineering Portfolio"
                subheading={`Version ${APP_VERSION}`}
              />
            }
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
          update ? (
            <Banner
              status="info"
              title={`New version ${update.latest_version} is available`}
              description={`You are running ${update.current_version}.`}
              endContent={<Button label="Update now" variant="primary" isLoading={isUpdating} onClick={() => void handleUpdate()} />}
            />
          ) : INFO_MESSAGE ? <Banner status="info" title={INFO_MESSAGE} /> : undefined
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
