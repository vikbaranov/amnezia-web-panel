# Responsive PWA for WebUI — Design

Date: 2026-08-22
Status: Approved

## Goal

Turn the Amnezia Web Panel into an installable, responsive Progressive Web App
that works well on mobile, while preserving the existing desktop experience.

## Constraints & context

- Server-rendered FastAPI + Jinja2 app. Data lives on remote Ubuntu servers
  reached over SSH, so true offline data is impossible. PWA scope is
  **installable + app-shell caching**, not full offline data.
- `app.py` is the monolith entrypoint; `templates/base.html` is extended by all
  authenticated pages, `templates/login.html` is standalone.
- `site_settings` (`data.settings.appearance`) holds dynamic `title`, `logo`,
  `subtitle`; rendered into templates via `tpl()` in `app.py:1424`.
- Static assets mounted at `/static` (`app.py:97`). Custom CSS at
  `static/css/style.css` (~1868 lines) already has breakpoints at 720/768/480/900px.
- i18n via 5 JSON files in `translations/` (en, ru, fr, zh, fa — fa is RTL).

## Components

### 1. PWA manifest (dynamic route)

Add `GET /manifest.webmanifest` in `app.py`. Returns JSON derived from
`site_settings`:

- `name` = `site_settings.title`
- `short_name` = `site_settings.title`
- `description` = subtitle / localized site description
- `start_url` = `/`
- `display` = `standalone`
- `background_color` = `#0a0a0f`, `theme_color` = `#0a0a0f` (CSS `--bg-primary`)
- `icons` = references to `static/icons/*.png` (192, 512, maskable-512)

### 2. App icons (generated once, committed)

`static/icons/`: `icon-192.png`, `icon-512.png`, `maskable-512.png`,
`apple-touch-icon.png` (180). Generated from the existing `static/favicon.svg`
shield via a one-off script (Pillow if available, else macOS `sips`/`qlmanage`).
Committed so builds don't need to regenerate them.

### 3. Service worker — `static/sw.js`

- Cache-first for static assets (CSS, JS, icons, fonts).
- Network-first for HTML navigations with fallback to cached `offline.html`.
- Versioned cache (bump version constant) for clean updates on deploy.

### 4. Offline fallback

Standalone `templates/offline.html` (no auth) + `GET /offline` route. Cached by
the SW and served when a navigation fails while offline.

### 5. Meta tags & SW registration

In both `templates/base.html` and `templates/login.html` heads:

- `<link rel="manifest" href="/manifest.webmanifest">`
- `<meta name="theme-color">`
- `<meta name="mobile-web-app-capable" content="yes">`
- `<meta name="apple-mobile-web-app-capable" content="yes">`
- `<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">`
- `<meta name="apple-mobile-web-app-title">`
- `<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">`

Inline script registers `/static/sw.js` on load (both templates).

### 6. Install button

- Capture `beforeinstallprompt`; show a compact "Install" icon-button in the
  header (mobile only).
- Hide after `appinstalled` or dismissal.
- New i18n key `install_app`.

### 7. Responsive bottom nav + compact header

- Bottom tab bar (fixed, `env(safe-area-inset-bottom)`-aware) shown only
  ≤768px, rendering only role-appropriate links (Servers/Users/Settings/My
  Connections). Reuses existing `nav_*` i18n keys.
- Header becomes compact on mobile: logo + install/theme/lang/logout icon
  buttons; username and role badge hidden.
- Add bottom padding to `<main>` so content clears the fixed bar.
- Desktop nav unchanged.

### 8. i18n

New keys in all 5 translation files: `install_app`, `offline_title`,
`offline_message`.

## Error handling

- Manifest route must not require auth (browsers fetch it pre-login); read
  `load_data()` defensively (defaults already applied there).
- SW registration failures are silent (best-effort enhancement).
- `beforeinstallprompt` absence (iOS/desktop) simply leaves the button hidden.

## Testing

- Unit test: `GET /manifest.webmanifest` returns valid JSON with required PWA
  fields (`name`, `start_url`, `display`, `icons`).
- Manual: `/static/sw.js`, `/offline`, and icon files resolve with 200.

## Out of scope

- Push notifications.
- Offline data sync (impossible given server-side SSH model).
- Redesigning desktop layout.
