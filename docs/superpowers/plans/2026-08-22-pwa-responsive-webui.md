# Responsive PWA for WebUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Amnezia Web Panel an installable, responsive PWA with a mobile bottom nav, compact header, and app-shell offline caching.

**Architecture:** A small pure-Python module `pwa.py` builds the web manifest dict; `app.py` exposes `/manifest.webmanifest` and `/offline`. A static service worker `static/sw.js` does cache-first for assets and network-first for navigations with an offline fallback. Templates/CSS get mobile meta tags, an install button, and a fixed bottom tab bar (≤768px).

**Tech Stack:** FastAPI + Jinja2, vanilla JS service worker, existing `static/css/style.css`, `rsvg-convert` (installed at `/opt/homebrew/bin/rsvg-convert`) for icon generation.

---

## File Structure

**Create:**
- `pwa.py` — pure `build_webmanifest(site_settings)` function (no heavy deps)
- `static/icons/app-icon.svg` — 512px full-bleed icon source (shield at 80% for maskable safe zone)
- `static/icons/icon-192.png`, `icon-512.png`, `maskable-512.png`, `apple-touch-icon.png` — generated PNGs (committed)
- `static/sw.js` — service worker
- `templates/offline.html` — standalone offline fallback page
- `tests/test_pwa.py` — unit tests for `build_webmanifest`

**Modify:**
- `app.py` — import `build_webmanifest`, add `/manifest.webmanifest` and `/offline` routes
- `templates/base.html` — meta tags, SW registration, install button, bottom nav
- `templates/login.html` — meta tags, SW registration
- `static/css/style.css` — bottom nav, compact header, install button, safe-area
- `translations/en.json`, `ru.json`, `fr.json`, `zh.json`, `fa.json` — 3 new keys each

---

### Task 1: Manifest builder module (TDD)

**Files:**
- Create: `pwa.py`
- Create: `tests/test_pwa.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from pwa import build_webmanifest


class BuildWebmanifestTest(unittest.TestCase):
    def test_returns_required_pwa_fields(self):
        manifest = build_webmanifest({'title': 'My Panel', 'subtitle': 'VPN'})

        self.assertEqual(manifest['name'], 'My Panel')
        self.assertEqual(manifest['short_name'], 'My Panel')
        self.assertEqual(manifest['start_url'], '/')
        self.assertEqual(manifest['scope'], '/')
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['background_color'], '#0a0a0f')
        self.assertEqual(manifest['theme_color'], '#0a0a0f')

    def test_icons_have_required_sizes_and_purposes(self):
        manifest = build_webmanifest({'title': 'My Panel'})
        sizes = {icon['sizes'] for icon in manifest['icons']}
        purposes = {icon['purpose'] for icon in manifest['icons']}

        self.assertIn('192x192', sizes)
        self.assertIn('512x512', sizes)
        self.assertIn('any', purposes)
        self.assertIn('maskable', purposes)

    def test_defaults_when_settings_empty(self):
        manifest = build_webmanifest({})

        self.assertEqual(manifest['name'], 'Amnezia Panel')
        self.assertTrue(manifest['description'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_pwa -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pwa'`

- [ ] **Step 3: Write the module**

```python
ICONS = [
    {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    {"src": "/static/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
]


def build_webmanifest(site_settings):
    settings = site_settings or {}
    title = settings.get('title') or 'Amnezia Panel'
    subtitle = settings.get('subtitle') or ''
    description = f'{title} — {subtitle}'.strip(' —')

    return {
        "name": title,
        "short_name": title,
        "description": description,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0a0a0f",
        "theme_color": "#0a0a0f",
        "icons": ICONS,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_pwa -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pwa.py tests/test_pwa.py
git commit -m "feat: add web manifest builder for PWA"
```

---

### Task 2: App icons

**Files:**
- Create: `static/icons/app-icon.svg`
- Create: `static/icons/icon-192.png`, `icon-512.png`, `maskable-512.png`, `apple-touch-icon.png`

- [ ] **Step 1: Write the icon SVG source**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#8b5cf6"/>
      <stop offset="100%" stop-color="#6366f1"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" fill="url(#g)"/>
  <g transform="translate(16 16) scale(0.8) translate(-16 -16)">
    <path d="M16 6C12.5 6 9.5 7.2 8 8v10c0 4.5 3.5 7.5 8 10 4.5-2.5 8-5.5 8-10V8c-1.5-.8-4.5-2-8-2z" fill="none" stroke="rgba(255,255,255,0.9)" stroke-width="1.5"/>
    <path d="M16 10c-2.5 0-4.5.8-5.5 1.3v6.7c0 3 2.2 5.2 5.5 7 3.3-1.8 5.5-4 5.5-7v-6.7c-1-.5-3-1.3-5.5-1.3z" fill="rgba(255,255,255,0.15)"/>
  </g>
</svg>
```

- [ ] **Step 2: Generate the PNGs**

```bash
mkdir -p static/icons && \
rsvg-convert -w 192 -h 192 static/icons/app-icon.svg -o static/icons/icon-192.png && \
rsvg-convert -w 512 -h 512 static/icons/app-icon.svg -o static/icons/icon-512.png && \
rsvg-convert -w 512 -h 512 static/icons/app-icon.svg -o static/icons/maskable-512.png && \
rsvg-convert -w 180 -h 180 static/icons/app-icon.svg -o static/icons/apple-touch-icon.png
```

- [ ] **Step 3: Verify the PNGs exist and are non-empty**

Run: `ls -la static/icons/`
Expected: 5 files including 4 `.png` each > 1KB

- [ ] **Step 4: Commit**

```bash
git add static/icons/
git commit -m "feat: add PWA app icons"
```

---

### Task 3: Offline page + route

**Files:**
- Create: `templates/offline.html`
- Modify: `app.py`

- [ ] **Step 1: Write the offline page**

```html
<!DOCTYPE html>
<html lang="{{ lang }}" {% if lang=='fa' %}dir="rtl" {% endif %}>

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ site_settings.title or 'Amnezia Panel' }} — {{ _('offline_title') }}</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="stylesheet" href="/static/css/style.css">
    <script>!function () { var t = localStorage.getItem('theme') || 'dark'; document.documentElement.setAttribute('data-theme', t) }()</script>
    <style>
        .offline-wrapper {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: var(--space-lg);
            background: var(--bg-primary);
            text-align: center;
        }
        .offline-card { max-width: 360px; width: 100%; }
        .offline-icon { font-size: 3rem; margin-bottom: var(--space-md); }
        .offline-card h1 { font-size: 1.3rem; margin-bottom: var(--space-sm); color: var(--text-primary); }
        .offline-card p { color: var(--text-secondary); margin-bottom: var(--space-lg); }
    </style>
</head>

<body>
    <div class="offline-wrapper">
        <div class="offline-card">
            <div class="offline-icon">📡</div>
            <h1>{{ _('offline_title') }}</h1>
            <p>{{ _('offline_message') }}</p>
            <button class="btn btn-primary" onclick="location.reload()">{{ _('refresh') }}</button>
        </div>
    </div>
</body>

</html>
```

- [ ] **Step 2: Add the import and routes to `app.py`**

Add the import after `import telegram_bot as tg_bot` (line 45):

```python
from pwa import build_webmanifest
```

Add the routes after the `logout` route (after line 1926):

```python
@app.get('/offline', response_class=HTMLResponse, tags=["System Templates"])
async def offline_page(request: Request):
    return tpl(request, 'offline.html')


@app.get('/manifest.webmanifest', tags=["System Templates"])
async def manifest():
    data = load_data()
    site_settings = data.get('settings', {}).get('appearance', {})
    return build_webmanifest(site_settings)
```

- [ ] **Step 3: Verify the app compiles**

Run: `python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"`
Expected: no output (success)

- [ ] **Step 4: Commit**

```bash
git add templates/offline.html app.py
git commit -m "feat: add offline fallback page and manifest route"
```

---

### Task 4: Service worker

**Files:**
- Create: `static/sw.js`

- [ ] **Step 1: Write the service worker**

```js
const CACHE_NAME = 'amnezia-panel-v1';
const APP_SHELL = [
  '/offline',
  '/static/css/style.css',
  '/static/js/qrcode.min.js',
  '/static/favicon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/maskable-512.png',
  '/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(APP_SHELL.map((url) => cache.add(url).catch(() => {})))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return res;
        })
        .catch(() => caches.match('/offline'))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((res) => {
        if (res.ok && url.pathname.startsWith('/static/')) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return res;
      });
    })
  );
});
```

- [ ] **Step 2: Verify the file is served**

Run: `python3 app.py` (temporarily), then `curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/static/sw.js` — stop the server afterwards.
Expected: `200`

- [ ] **Step 3: Commit**

```bash
git add static/sw.js
git commit -m "feat: add service worker with app-shell caching"
```

---

### Task 5: Meta tags + SW registration in templates

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/login.html`

- [ ] **Step 1: Add PWA meta tags to `base.html` head**

Insert after the favicon link (line 8, `<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">`):

```html
    <link rel="manifest" href="/manifest.webmanifest">
    <meta name="theme-color" content="#0a0a0f">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="{{ site_settings.title or 'Amnezia Panel' }}">
    <link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
```

- [ ] **Step 2: Add the same meta tags to `login.html` head**

Insert after `<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">` (line 8):

```html
    <link rel="manifest" href="/manifest.webmanifest">
    <meta name="theme-color" content="#0a0a0f">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="{{ site_settings.title or 'Amnezia Panel' }}">
    <link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
```

- [ ] **Step 3: Add SW registration script to `base.html` before `</body>`**

Insert before the final `</body>` tag (after `{% block scripts %}{% endblock %}`):

```html
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/static/sw.js').catch(() => {});
            });
        }
    </script>
```

- [ ] **Step 4: Add SW registration script to `login.html` before `</body>`**

Find the end of `login.html` and insert before `</body>`:

```html
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/static/sw.js').catch(() => {});
            });
        }
    </script>
```

- [ ] **Step 5: Commit**

```bash
git add templates/base.html templates/login.html
git commit -m "feat: add PWA meta tags and service worker registration"
```

---

### Task 6: Install button

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add install buttons to both header `.nav-user` blocks**

In the logged-in `.nav-user` block, insert after the theme-toggle button (after `<button class="theme-toggle" onclick="toggleTheme()" title="{{ _('toggle_theme') }}" id="themeToggle">🌙</button>`):

```html
                <button class="theme-toggle install-button" id="installButton" style="display:none; margin-right: var(--space-sm);" title="{{ _('install_app') }}">📲</button>
```

In the logged-out `.nav-user` block, insert after the same theme-toggle button:

```html
                <button class="theme-toggle install-button" id="installButton" style="display:none; margin-right: var(--space-sm);" title="{{ _('install_app') }}">📲</button>
```

Note: only one of these two blocks renders per page load (they are mutually exclusive via `{% if current_user %}`), so there is no duplicate `id`.

- [ ] **Step 2: Add install-button logic before `{% block scripts %}`**

Insert before `{% block scripts %}{% endblock %}` (line 273):

```html
    <script>
        /* ===== PWA Install Prompt ===== */
        (function () {
            let deferredPrompt = null;
            const installButton = document.getElementById('installButton');

            window.addEventListener('beforeinstallprompt', (e) => {
                e.preventDefault();
                deferredPrompt = e;
                if (installButton) installButton.style.display = '';
            });

            window.addEventListener('appinstalled', () => {
                deferredPrompt = null;
                if (installButton) installButton.style.display = 'none';
            });

            if (installButton) {
                installButton.addEventListener('click', async () => {
                    if (!deferredPrompt) return;
                    deferredPrompt.prompt();
                    await deferredPrompt.userChoice;
                    deferredPrompt = null;
                    installButton.style.display = 'none';
                });
            }
        })();
    </script>
```

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add in-app PWA install button"
```

---

### Task 7: Bottom nav + compact header

**Files:**
- Modify: `templates/base.html`
- Modify: `static/css/style.css`

- [ ] **Step 1: Add the bottom nav markup after `</main>`**

Insert after `</main>` (line 81):

```html
        {% if current_user %}
        <nav class="bottom-nav" id="bottomNav">
            {% if current_user.role in ['admin', 'support'] %}
            <a href="/" class="bottom-nav-link">
                <span class="bottom-nav-icon">🖥️</span>
                <span>{{ _('nav_servers') }}</span>
            </a>
            <a href="/users" class="bottom-nav-link">
                <span class="bottom-nav-icon">👥</span>
                <span>{{ _('nav_users') }}</span>
            </a>
            {% endif %}
            {% if current_user.role == 'admin' %}
            <a href="/settings" class="bottom-nav-link">
                <span class="bottom-nav-icon">⚙️</span>
                <span>{{ _('nav_settings') }}</span>
            </a>
            {% endif %}
            <a href="/my" class="bottom-nav-link">
                <span class="bottom-nav-icon">🔌</span>
                <span>{{ _('nav_connections') }}</span>
            </a>
        </nav>
        {% endif %}
```

- [ ] **Step 2: Extend the active-nav script to include bottom-nav links**

Change the active-nav selector in `base.html` from:

```js
            document.querySelectorAll('.nav-link').forEach(link => {
```

to:

```js
            document.querySelectorAll('.nav-link, .bottom-nav-link').forEach(link => {
```

- [ ] **Step 3: Add bottom-nav and compact-header CSS**

Append to the end of `static/css/style.css`:

```css
/* ===== PWA Bottom Navigation (mobile) ===== */
.bottom-nav {
    display: none;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
    padding: 4px 8px;
    padding-bottom: calc(4px + env(safe-area-inset-bottom));
    backdrop-filter: blur(12px);
}

.bottom-nav-link {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 4px;
    font-size: 0.62rem;
    font-weight: 500;
    color: var(--text-muted);
    text-decoration: none;
    border-radius: var(--radius-sm);
}

.bottom-nav-icon {
    font-size: 1.2rem;
    line-height: 1;
}

.bottom-nav-link.active {
    color: var(--accent-light);
    background: rgba(139, 92, 246, 0.08);
}

/* ===== Install button ===== */
.install-button {
    cursor: pointer;
}

@media (max-width: 768px) {
    .bottom-nav {
        display: flex;
    }

    .app-container {
        padding-bottom: calc(90px + env(safe-area-inset-bottom));
    }

    .app-header {
        flex-direction: row;
        align-items: center;
        gap: var(--space-sm);
    }

    .logo-subtitle {
        display: none;
    }

    .header-nav {
        display: none;
    }

    .nav-user {
        border-left: none;
        margin-left: auto;
        padding-left: 0;
    }

    .nav-username,
    .nav-user .badge {
        display: none;
    }
}
```

- [ ] **Step 4: Verify templates still compile**

Run: `python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"`
Expected: no output (success)

- [ ] **Step 5: Commit**

```bash
git add templates/base.html static/css/style.css
git commit -m "feat: add mobile bottom nav and compact header"
```

---

### Task 8: i18n keys

**Files:**
- Modify: `translations/en.json`, `ru.json`, `fr.json`, `zh.json`, `fa.json`

- [ ] **Step 1: Add the three keys to each file**

For each file, add `install_app` immediately after the existing `"install": "..."` line, and `offline_title` + `offline_message` immediately after the existing `"offline": "..."` line. Exact strings per language:

**en.json**
```json
  "install_app": "Install app",
```
```json
  "offline_title": "You're offline",
  "offline_message": "Check your connection and try again.",
```

**ru.json**
```json
  "install_app": "Установить приложение",
```
```json
  "offline_title": "Вы не в сети",
  "offline_message": "Проверьте подключение и повторите попытку.",
```

**fr.json**
```json
  "install_app": "Installer l'application",
```
```json
  "offline_title": "Vous êtes hors ligne",
  "offline_message": "Vérifiez votre connexion et réessayez.",
```

**zh.json**
```json
  "install_app": "安装应用",
```
```json
  "offline_title": "您已离线",
  "offline_message": "请检查网络连接后重试。",
```

**fa.json**
```json
  "install_app": "نصب برنامه",
```
```json
  "offline_title": "آفلاین هستید",
  "offline_message": "اتصال خود را بررسی کرده و دوباره تلاش کنید.",
```

- [ ] **Step 2: Validate JSON is still parseable in all five files**

Run: `python3 -c "import json; [json.load(open(f'translations/{l}.json')) for l in ['en','ru','fr','zh','fa']]; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add translations/
git commit -m "feat: add PWA i18n keys (install_app, offline_title, offline_message)"
```

---

### Task 9: Verification

- [ ] **Step 1: Compile-check all Python**

Run: `python3 -c "import py_compile; py_compile.compile('app.py', doraise=True); py_compile.compile('pwa.py', doraise=True)"`
Expected: no output

- [ ] **Step 2: Run the test suites**

Run: `python3 -m unittest tests.test_pwa tests.test_connection_service tests.test_telegram_self_service tests.test_awg_manager_ip_allocation -v`
Expected: all pass (telegram suite requires `httpx` installed)

- [ ] **Step 3: Smoke-test routes manually**

Run: `python3 app.py`, then in another shell:
- `curl -s http://localhost:5000/manifest.webmanifest | python3 -m json.tool`
- `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/static/sw.js`
- `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/static/icons/icon-512.png`
- `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/offline`
Expected: valid manifest JSON with `name`/`start_url`/`icons`; `200` for the other three.

- [ ] **Step 4: Final commit (if any changes)**

```bash
git status && git add -A && git commit -m "chore: final PWA verification" || echo "nothing to commit"
```

---

## Self-Review Notes

- Spec coverage: manifest (Task 1/3), icons (Task 2), service worker (Task 4), offline page (Task 3), meta tags + SW registration (Task 5), install button (Task 6), bottom nav + compact header (Task 7), i18n (Task 8), testing (Task 9). All spec sections covered.
- `theme_color`/`background_color` pinned to `#0a0a0f` (`--bg-primary`), matching the spec.
- `build_webmanifest` is imported in `app.py` and tested independently in `tests/test_pwa.py`, avoiding heavy `app` import in tests.
