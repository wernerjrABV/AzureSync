# Synchronization Card Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the synchronization card status badge and display synchronization intervals as `HH:MM`.

**Architecture:** Keep the existing `SynchronizationPage` component and Astryx layout primitives. Add a pure formatting helper in the page module, cover it through rendered-page behavior, and change only the card markup.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, Astryx Design System.

## Global Constraints

- Use exclusively Astryx components for the UI.
- Do not add custom CSS, inline styles, styled-components, or emotion.
- Preserve existing synchronization behavior and API contracts.

---

### Task 1: Add failing synchronization-card assertions

**Files:**
- Modify: `apps/web-read/src/pages/SynchronizationPage.test.tsx`
- Test: `apps/web-read/src/pages/SynchronizationPage.test.tsx`

**Interfaces:**
- Consumes: the existing `SyncAreaPath` fixture and rendered `SynchronizationPage`.
- Produces: regression coverage requiring `Every 00:30` for a 30-minute interval and a status badge rendered before the area path in the card DOM.

- [ ] **Step 1: Write the failing tests**

Extend the existing metadata test fixture with assertions:

```tsx
expect(screen.getByText("Every 00:30")).toBeInTheDocument();
const card = screen.getByText("Intake\\\\Platform").closest("div");
expect(card).not.toBeNull();
expect(card!.textContent!.indexOf("Inactive")).toBeLessThan(card!.textContent!.indexOf("Intake\\\\Platform"));
```

Add a second interval case using `intervalo_minutos: 90` and assert:

```tsx
expect(screen.getByText("Every 01:30")).toBeInTheDocument();
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- --run src/pages/SynchronizationPage.test.tsx`

Expected: FAIL because the current UI renders `Every 30 min`, and the status badge is after the area path in the same row.

- [ ] **Step 3: Commit the failing-test changes**

```bash
git add apps/web-read/src/pages/SynchronizationPage.test.tsx
git commit -m "test: specify synchronization card layout"
```

### Task 2: Implement card layout and interval formatting

**Files:**
- Modify: `apps/web-read/src/pages/SynchronizationPage.tsx`

**Interfaces:**
- Consumes: `SyncAreaPath.intervalo_minutos`, `ativo`, and existing Astryx layout components.
- Produces: `formatSyncInterval(totalMinutes: number): string` and the updated card presentation.

- [ ] **Step 1: Add the minimal formatter**

Add this pure helper near the existing status helpers:

```tsx
function formatSyncInterval(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}
```

- [ ] **Step 2: Reorganize the card header using Astryx primitives**

Replace the current combined header row with:

```tsx
<VStack gap={1}>
  <HStack justify="end" align="center">
    <Badge
      variant={areaPath.ativo ? "success" : "neutral"}
      label={areaPath.ativo ? "Active" : "Inactive"}
    />
  </HStack>
  <Text as="h2" type="large" weight="semibold">{areaPath.area_path}</Text>
  <Text type="supporting">{areaPath.organization} / {areaPath.project}</Text>
  <HStack gap={2} align="center" wrap="wrap">
    <Badge
      variant={areaPath.is_running ? "warning" : statusVariant(areaPath.last_sync_status)}
      label={areaPath.is_running ? "Running" : areaPath.last_sync_status ?? "Not synchronized"}
    />
    <Text type="supporting">Every {formatSyncInterval(areaPath.intervalo_minutos)}</Text>
  </HStack>
</VStack>
```

- [ ] **Step 3: Run the focused tests**

Run: `npm test -- --run src/pages/SynchronizationPage.test.tsx`

Expected: PASS, including the new layout and `HH:MM` assertions.

- [ ] **Step 4: Run build and the complete web test suite**

Run: `npm test -- --run` and `npm run build`

Expected: all Vitest tests pass and TypeScript/Vite build completes successfully.

- [ ] **Step 5: Commit the implementation**

```bash
git add apps/web-read/src/pages/SynchronizationPage.tsx apps/web-read/src/pages/SynchronizationPage.test.tsx
git commit -m "feat: refine synchronization card status layout"
```
