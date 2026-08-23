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
