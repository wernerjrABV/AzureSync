# Collapsible Astryx Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the web-read Astryx sidebar start collapsed on every application load while retaining the official Astryx toggle.

**Architecture:** Configure the existing `SideNav` in `apps/web-read/src/App.tsx` with Astryx's uncontrolled `collapsible` configuration and `defaultIsCollapsed: true`. Add a focused frontend regression test around the rendered shell behavior; no application state, persistence, or custom styling is needed.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, `@astryxdesign/core` 0.1.6.

## Global Constraints

- Use exclusively Astryx components for UI behavior and presentation.
- Do not add CSS, inline styles, or new runtime dependencies.
- The initial state must be collapsed on each mount; do not persist it.
- Keep the existing navigation selection behavior unchanged.

### Task 1: Configure and verify the default collapsed state

**Files:**
- Modify: `apps/web-read/src/App.tsx`
- Test: `apps/web-read/src/App.test.tsx` (create if absent)

**Interfaces:**
- Consumes: existing `AppShell`, `SideNav`, and `SideNavItem` composition.
- Produces: a `SideNav` configured as `collapsible={{ defaultIsCollapsed: true }}` with the built-in Astryx collapse button enabled.

- [ ] **Step 1: Write the failing regression test**

  Add a focused test that renders the relevant Astryx `SideNav` configuration and asserts the initial DOM has the collapsed navigation width class/state and exposes the official collapse button. Use the installed package's public behavior rather than custom implementation details where possible.

- [ ] **Step 2: Run the focused test and verify it fails for the missing configuration**

  Run from `apps/web-read`:

  ```powershell
  npm test -- src/App.test.tsx
  ```

  Expected result: the new assertion for the collapsed initial state fails while the existing app behavior remains renderable.

- [ ] **Step 3: Apply the minimal implementation**

  Update the existing `SideNav` opening tag in `apps/web-read/src/App.tsx`:

  ```tsx
  <SideNav collapsible={{defaultIsCollapsed: true}}>
  ```

  Leave `AppShell`, navigation items, page state, and all styling untouched.

- [ ] **Step 4: Run the focused test and the full frontend verification**

  ```powershell
  npm test -- src/App.test.tsx
  npm run build
  npm test
  ```

  Expected result: the focused test, TypeScript/Vite build, and complete Vitest suite exit successfully.

- [ ] **Step 5: Inspect the diff**

  ```powershell
  git diff --check
  git diff -- apps/web-read/src/App.tsx apps/web-read/src/App.test.tsx
  ```

  Confirm that only the requested Astryx configuration and its regression test are present.

