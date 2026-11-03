# Design system

The web UI (`src/ui/static/`) uses a small design system built from plain CSS custom properties. The goal is an interface that feels light, calm and approachable. It is monochrome by default and easy to re-brand.

A live reference of every token and component is served at **`/static/design-system.html`** on any running instance. It includes a light/dark switch and a brand-colour playground.

## Principles

- **Monochrome first.** A soft, slightly warm neutral scale carries the whole interface. The only hues are the three semantic families (green = success, orange = warning, red = danger). They always appear as soft tints with a darker, readable foreground, never as loud solid fills. "Info" is neutral.
- **Colour means an outcome, not a state.** "Enabled", "Running" and "Public" are states, so they use the neutral `.badge-on` look; "Disabled" and "Private" use `.badge-off`. Green is kept for real successes (a test passed, a run completed, an account is connected), orange for things that need attention and red for failures.
- **One accent, swappable.** Everything that signals "primary" or "active" reads from a single `--color-accent` token. By default that is the ink colour itself.
- **Accessible by default.** Text meets WCAG AA in both themes. Input and toggle edges meet 3:1 non-text contrast. Every control has a visible `:focus-visible` ring, touch targets are 44px on phones, and `prefers-reduced-motion` is respected.
- **Whitespace over chrome.** Content sits directly on the canvas and is grouped in white cards with a hairline border. Shadows are soft and used sparingly.
- **Inter, self-hosted.** Inter (variable, SIL OFL) ships in `static/fonts/`, so there are no third-party font requests and the PWA works offline. Stylistic sets `cv05` (tailed *l*) and `cv11` (single-storey *a*) are enabled for legibility and a friendlier texture.
- **Monospace only for real code.** Inline `<code>` in the interface (tool names, cron expressions) is set in Inter on a subtle chip. Geist Mono (self-hosted, SIL OFL) is used only for code blocks, inline code inside chat replies, the log stream and JSON editors.
- **Lucide icons only.** Every icon comes from [Lucide](https://lucide.dev) (ISC). No emoji or Unicode glyphs stand in for icons.

## Files and load order

Every page loads, in this order:

| File | Purpose |
| --- | --- |
| `js/theme.js` | Resolves light/dark/system before first paint and sets `<html data-theme>`. |
| `css/tokens.css` | All design tokens: colour (light and dark), type, spacing, radius, elevation, motion, layers. |
| `css/base.css` | `@font-face`, reset, document and typography defaults, focus, scrollbars, keyframes. |
| `css/components.css` | Reusable, page-agnostic components (see below). |
| `css/common.css` | App patterns: app shell and navigation, conversation sidebar, Settings building blocks. |
| `css/mobile.css` | Touch targets, safe areas, mobile menu, bottom-sheet modals. |
| `css/pages/*.css` | Optional page-specific styles (`chat.css`, `monitoring.css`, `artifacts.css`). |

`artifact-unlock.html` is served to anonymous visitors and must stay self-contained. It mirrors the few tokens it needs inline and embeds the Inter latin subset as a data URI.

## Tokens

Only use **semantic** tokens in component and page CSS. Never use raw colour values (hex, `rgb()`, `hsl()`) or the `--gray-*` / `--green-*` / `--orange-*` / `--red-*` primitives. `tokens.css` is the only file allowed to contain raw values.

| Group | Tokens |
| --- | --- |
| Surfaces | `--color-bg` (canvas), `--color-surface` (cards), `--color-surface-raised` (dialogs), `--color-sunken` (wells, code), `--color-overlay` (modal backdrop) |
| Text | `--color-text`, `--color-text-secondary`, `--color-text-tertiary`, `--color-text-disabled`, `--color-text-inverse` |
| Borders | `--color-border-subtle`, `--color-border`, `--color-border-strong`, `--color-border-control` (3:1 for inputs) |
| Interaction | `--color-fill-hover`, `--color-fill-active`, `--color-focus-ring`, `--color-focus-border` and `--color-focus-ring-soft` (text inputs), `--color-tab-active` (selected segment) |
| Accent | `--color-accent`, `--color-on-accent`, `--color-accent-hover`, `--color-accent-subtle`, `--color-accent-muted` |
| Semantic | `--color-{success,warning,danger,neutral}-{fg,bg,border,solid}` |
| Destructive | `--color-danger-emphasis`, `--color-danger-emphasis-hover`, `--color-on-danger` (the solid red confirm button only) |
| Fixed | `--color-qr-bg`, `--color-qr-fg` (QR codes stay dark on light), `--color-knob`, `--shadow-knob` (toggle knob) |
| Type | `--font-sans`, `--font-mono`, `--text-xs` … `--text-2xl`, `--leading-*`, `--weight-*`, `--tracking-*` |
| Space | `--space-0-5` (2px) … `--space-16` (64px) |
| Shape | `--radius-xs` … `--radius-xl`, `--radius-full`, `--control-h-{sm,md,lg}` |
| Layout | `--content-max`, `--content-narrow`, `--nav-width`, `--nav-width-collapsed`, `--topbar-h` |
| Elevation | `--shadow-xs`, `--shadow-sm`, `--shadow-md`, `--shadow-lg` |
| Motion | `--ease-out`, `--duration-fast`, `--duration-base`, `--duration-slow` |
| Layers | `--z-sticky`, `--z-nav`, `--z-modal`, `--z-toast` (small integers are fine for stacking inside one component) |

Font sizes always come from `--text-*`. Relative units (`em`, `%`) are fine for prose inside a component, such as headings in a chat reply.

### Dark mode

Dark mode overrides colour tokens only, under `:root[data-theme="dark"]`. When you add a colour token that points at a primitive, define it in the dark block too.

The same dark block is repeated under `@media (prefers-color-scheme: dark) { :root:not([data-theme]) { … } }`. That copy applies only when `theme.js` hasn't run, so the OS preference still works without JavaScript. The two blocks must be identical, and a test enforces it.

A few files keep copies of token values because they can't load `tokens.css`: `theme.js` and the `theme-color` meta tags (the canvas colour), `manifest.json` and `src/api/pwa.py` (the PWA colours), and `artifact-unlock.html` (a self-contained page). A test checks every copy against `tokens.css`, so after changing a token, update those copies too.

## Adding a brand accent

The baseline is intentionally monochrome. To give an installation its own accent, define two variables after `tokens.css` loads:

```css
:root {
    --brand: #3b5bdb;          /* the accent */
    --brand-contrast: #ffffff; /* readable text on top of it */
}
```

Primary buttons, toggles, checkboxes, the active navigation icon, the logo tile, focus rings and accent tints all derive from these two variables through `color-mix()`. No other change is needed. Pick a brand colour that has at least 4.5:1 contrast with `--brand-contrast` and 3:1 against the page background.

A brand that works on the light canvas is often too dark on the dark one. Give the dark theme its own variant with two optional variables, which fall back to `--brand` and `--brand-contrast`:

```css
:root {
    --brand-dark: #91a7ff;
    --brand-dark-contrast: #121211;
}
```

## Components

All components live in `css/components.css`. Variants only set private custom properties (`--_btn-*`, `--_badge-*`, `--_alert-*`), and the base rule is the only place that paints. To add a variant, set those properties; don't restyle the component.

| Component | Markup |
| --- | --- |
| Button | `.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-danger` / `.btn-destructive`, sizes `.btn-sm` / `.btn-lg`, `.btn-block`; icon-only `.btn-icon` (always square, quiet unless combined with a variant); `.job-action-btn` for compact table row actions |
| Form | `.form-group` > `.form-label` + `.form-input` / `.form-select` / `.form-textarea` + `.form-hint`; `.input-group`; `.form-control-sm` for compact filters |
| Toggle | `label.toggle-label` > `input.toggle-input` + `span.toggle-slider` (+ `span.toggle-text`) |
| Checkbox / radio | Native inputs (tinted via `accent-color`), `.checkbox-label`, `.radio-label`, `.radio-group` |
| Card | `.card` (+ `.card-header`, `.card-footer`, `.card-flush` for edge-to-edge tables), `.stat-card` |
| Badge | `.badge` + `.badge-{success,warning,danger,neutral}` for outcomes, `.badge-on` / `.badge-off` for states, `.badge-outline`, `.badge-sm`; optional `.status-dot` inside. For job and run statuses use `statusBadgeClass(status)` from `js/components.js`. |
| Alert | `.alert` (info, neutral) + `.alert-{success,warning,danger}` |
| Tabs | `.tabs` > `button.tab(.active)`, a segmented control |
| Table | `.table` (or legacy `.jobs-table`); add `.table-stack` + `data-label` on cells to stack into cards on phones. Leave `data-label` off the name cell: in the card it becomes the first row, without a label. A row without actions shows `<span class="text-tertiary cell-placeholder">—</span>` in its actions cell; cards leave that row out. An on/off state is a switch in the first column (header `<span class="sr-only">Enabled</span>`), not a status badge plus an Enable/Disable button |
| Modal | `.modal` > `.modal-content` > `.modal-header` / `.modal-body` / `.modal-footer`; `ModalManager` in `common.js` produces the same look |
| Toast | `toast.success()` / `.error()` / `.warning()` / `.info()` from `common.js` |
| Feedback | `.spinner`, `.skeleton`, `.empty-state` |
| Utilities | Text: `.text-secondary`, `.text-tertiary`, `.text-success`, `.text-danger`, `.text-sm`, `.text-xs`, `.font-medium`. Spacing: `.mt-0` … `.mt-3`, `.mb-0` … `.mb-3`. Layout: `.flex`, `.flex-col`, `.gap-1` … `.gap-4`, `.grow`, `.self-start`, `.form-grid-2`. Width: `.measure-{sm,md,lg}`. Accessibility: `.sr-only`. |

### No inline styles

Markup (HTML files and the template strings in `js/`) never carries a `style` attribute. Use a component, a utility or a page class instead. The one exception is passing data to CSS through a custom property, such as `style="--chip-color:${color}"`.

To show and hide things, use the `hidden` attribute (`el.hidden = true`), never `el.style.display`. Modals open and close by toggling `.active`. Transient animations, such as a toast or dialog leaving, are classes too (`.is-leaving`).

## Responsive layout

Components respond to **their own width**, not the viewport, using container queries:

| Container | Elements | Used for |
| --- | --- | --- |
| `card` | `.card`, `.settings-section`, `.agent-card`, `.integration-card` | Card-level reflow (headers, footers, action rows) at `@container card (max-width: 560px)` |
| `table` | `.table-scroll`, `.jobs-table-wrap`, `.audit-log` | Stacking `.table-stack` / `.jobs-table` rows into cards at `@container table (max-width: 640px)` |

A table in a narrow card therefore stacks even on a wide screen. A table only stacks when it sits inside one of the `table` wrappers.

Viewport media queries are for page chrome only: navigation, sidebars, page padding, touch targets and bottom-sheet modals. There is one breakpoint, **768px**: `(max-width: 768px)` for phones, `(min-width: 769px)` above that, and `(max-width: 1024px) and (min-width: 769px)` for tablets. Custom properties can't be used in `@media`, so a test checks that no other breakpoint creeps in.

## Buttons and actions

- **One primary action per area.** There are no green or orange buttons: colour means an outcome, and a button is not an outcome.
- **Delete and remove** are always a square trash icon button in the shaded red `.btn-danger` style, never a text button. Use `trashButton(onclick, label)` from `js/components.js`; the label becomes the tooltip and accessible name. Inside tables pass `'job-action-btn'` as the third argument.
- **Destructive confirmations** (the "Delete", "Reset" or "Stop" button inside a confirm dialog) use the solid red `.btn-destructive`. Ask with `await modal.ask(title, message, { confirmText, danger: true })` instead of `window.confirm()`.
- **Icon buttons are square.** `.btn-icon` is 40×40 (32×32 with `.btn-sm`, 44×44 on touch screens). Combine it with a variant (`.btn .btn-danger .btn-icon`) to keep that variant's colours.
- **Button groups are right-aligned**: modal footers, card footers, `.btn-row`, `.settings-actions` and table row actions. In tables the last column fills the remaining width and its actions sit flush right; wide tables scroll horizontally inside `.table-scroll` / `.jobs-table-wrap`. The actions column header is screen-reader only (`<th><span class="sr-only">Actions</span></th>`), and a stacked card shows its actions without a label.

## Icons

Icons are [Lucide](https://lucide.dev) (ISC licence), bundled as an inline SVG sprite in `js/components.js` and generated from `lucide-static` 0.468.0. The design-system page lists every available icon.

- In JavaScript: `icon('check')` returns the markup, and `icon('loader', 'icon-spin')` adds a class. Add `icon-filled` for a solid closed shape, e.g. `icon('play', 'icon-filled')`.
- In HTML: `<svg class="icon" aria-hidden="true"><use href="#icon-check"></use></svg>`.
- Icons inherit `currentColor`. The `.icon` class sets a 1.75 stroke and a size of 1.15em; override `width`/`height` per context.
- Services, agents and plugins map to Lucide icons in `getServiceIcon()` and `getAgentIcon()` (`js/settings.js`). The sprite ids are prefixed with `svc-` and `agent-`.
- To add an icon, copy the inner elements of `lucide-static/icons/<name>.svg` into a new `<symbol id="icon-<name>" viewBox="0 0 24 24">`. Leave out presentation attributes so CSS can style it.
- Data-URI icons in CSS (the select chevron and the sidebar search) use the same Lucide paths.

## Writing UI copy

Use sentence case for titles, subtitles, buttons, tabs, table headers and form labels ("Add agent", not "Add Agent"). Product names and acronyms keep their capitals ("Google Ads", "API key"). Keep subtitles short; they wrap at 60 characters. Keep labels short and friendly, and say what will happen ("Yes, stop it" rather than "OK").

## Enforcement

`tests/test_design_system.py` runs with the rest of the test suite in CI. It checks that:

- no CSS outside `tokens.css` uses a raw colour or a palette primitive;
- every `var(--…)` reference points at a defined token (this catches typos, which otherwise fail silently);
- font sizes use `--text-*`, app-level `z-index` uses `--z-*`, and media queries use the shared breakpoints;
- the no-JS dark block matches the dark theme, and every colour token built on a primitive has a dark value;
- the hand-kept token copies (`theme.js`, the `theme-color` meta tags, `manifest.json`, `pwa.py`, `artifact-unlock.html`) match `tokens.css`;
- markup has no inline styles and no `style.display` toggles;
- no retired class or token name (below) comes back.

Run it on its own with `uv run pytest tests/test_design_system.py`.

## Retired names

These have been removed. The test fails if they reappear.

| Retired | Use instead |
| --- | --- |
| `.btn-success`, `.btn-warning`, `.btn-solid`, `.btn-neutral` | `.btn-primary` / `.btn-secondary`; a plain `.job-action-btn` is already neutral |
| `.status-badge`, `.status-badge-inline`, `.status-badge-*`, `.session-badge-*`, `.setting-source`, `.source-*` | `.badge` + a tone |
| `.status-enabled` / `.status-disabled`, `.badge-running` / `.badge-stopped` / `.badge-deleted` | `.badge-on` / `.badge-off` |
| `.status-success` / `.status-error` / `.status-warning` / `.status-info`, `.badge-error`, `.badge-pending`, `.badge-provisioning`, `.badge-accent` | `.badge-success` / `.badge-danger` / `.badge-warning` / `.badge-neutral` / `.badge-on`, or `statusBadgeClass()` |
| `.alert-error`, `.banner`, `.banner-warning`, `.info-box` | `.alert-danger`, `.alert-warning`, `.alert` |
| `--primary-color`, `--text-muted`, `--text-secondary`, `--border-color`, `--error-color`, `--success-color`, `--color-primary`, `--color-error`, `--radius`, `--shadow` and the other pre-redesign aliases | The semantic tokens above, e.g. `--color-accent`, `--color-text-secondary`, `--color-border`, `--color-danger-fg`, `--radius-md`, `--shadow-sm` |
| `@keyframes slideInRight`, `fadeIn` | `oa-slide-in-right`, `oa-fade-in` |
