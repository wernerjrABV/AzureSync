# Modern UI redesign — Area Paths page

## Goal
Restyle the single-page Flask UI (index + area path form) to feel modern and minimalist, using Inter font and a light Azure-blue/gray palette. Presentation-only change; no backend logic changes.

## Approach
- New `app/static/css/style.css`, linked from `index.html`'s `<head>` along with Google Fonts Inter (fallback `system-ui, sans-serif`).
- No JS framework, no build step. Collapsible form via native `<details>`/`<summary>`.

## Palette
- Background: `#f7f8fa`
- Card surface: `#ffffff`, 8px radius, soft box-shadow, no hard borders
- Primary accent (buttons, active status): Azure blue `#0078d4`
- Success status: soft green
- Failed/error status: soft red
- Secondary text: muted gray

## Layout
1. Header: "Area Paths" title + "+ Novo Area Path" button (toggles the `<details>` form panel open).
2. Auth error banner: soft rounded red alert (same conditional as today).
3. Area path list becomes a **card grid**, one card per area path:
   - Org / Project / Area path as card header
   - Status pill (ativo/inativo; last_sync_status colored)
   - Compact key-value details: sub-paths, intervalo, última sync, qtd processada, erro (if present)
   - Action buttons (Sincronizar, Editar, Excluir) styled as small primary/outline/danger-ghost buttons
4. Form panel: wrapped in `<details>` (open by default when `editing` is set), styled as a card matching the rest.

## Files touched
- New: `app/static/css/style.css`
- Edit: `app/templates/index.html`
- Edit: `app/templates/area_path_form.html`
- No routes.py changes beyond what's already staged (unrelated).
