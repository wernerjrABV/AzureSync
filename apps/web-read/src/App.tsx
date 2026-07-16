import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { AppShell } from "@astryxdesign/core/AppShell";
import { TopNav } from "@astryxdesign/core/TopNav";
import { TopNavHeading } from "@astryxdesign/core/TopNav";
import { SideNav } from "@astryxdesign/core/SideNav";
import { SideNavHeading } from "@astryxdesign/core/SideNav";
import { SideNavItem } from "@astryxdesign/core/SideNav";
import { Banner } from "@astryxdesign/core/Banner";
import WorkItemsListPage from "./pages/WorkItemsListPage";

const INFO_MESSAGE = "";

export default function App() {
  return (
    <Theme theme={neutralTheme}>
      <AppShell
        variant="elevated"
        contentPadding={4}
        topNav={
          <TopNav
            label="Main navigation"
            heading={<TopNavHeading heading="Work Items" />}
          />
        }
        sideNav={
          <SideNav header={<SideNavHeading heading="Work Items" />}>
            <SideNavItem label="Work Items" isSelected />
          </SideNav>
        }
        banner={
          INFO_MESSAGE ? <Banner status="info" title={INFO_MESSAGE} /> : undefined
        }
      >
        <WorkItemsListPage />
      </AppShell>
    </Theme>
  );
}
