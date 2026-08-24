# Self-Service Integration Design

## Context

The upstream repository ([PRVTPRO/Amnezia-Web-Panel](https://github.com/PRVTPRO/Amnezia-Web-Panel)) has the OpenAPI tag and scaffolding for Self-service but **no implementation**:

- Has: `GET /my`, `GET /api/my/connections`, `POST /api/my/connections/{id}/config`, `my_connections.html` template
- Has: `awg3` (AmneziaWG 3.1) protocol, WARP tunnels, marketplace, API tokens, sharing
- Missing: `connection_service.py`, all self-service business logic, admin settings UI, Telegram self-service wizard
- Missing: Self-service translation keys in `fr.json`, `zh.json`, `fa.json` (except `my_connections_title`, `no_connections_user_desc`, `show_config`)

The local repository has a complete self-service implementation that needs to be ported upstream.

## Architecture

```
connection_service.py (new file — NO import app)
  ↑ receives dependencies via injection:
    load_data, save_data, data_lock, get_ssh,
    get_protocol_manager, _manager_call, generate_vpn_link

app.py (upstream, ~6500 lines)
  ├── Import ConnectionService, DEFAULT_SELF_SERVICE_SETTINGS
  ├── Pydantic models: SelfServiceSettings, SelfServiceConnectionRequest
  ├── load_data() → self-service defaults + migrations
  ├── Instantiate ConnectionService
  ├── New routes: /api/my/connections/options, /api/my/connections/add, /api/my/connections/{id}/delete
  ├── /api/servers/{id}/edit → self_service_enabled field
  ├── /api/settings/save → self_service object
  └── launch_bot(..., self_service_svc=self_service_connections)

telegram_bot.py (upstream)
  ├── launch_bot: add self_service_svc=None parameter (backward compatible)
  ├── Self-service helper functions (_self_service_is_enabled, _get_eligible_servers, etc.)
  ├── Callback routing: user_create, user_create_server, user_create_protocol, user_add_client, user_delete, user_delete_confirm
  ├── _build_connections_keyboard: delete button for self-service connections
  └── Block self-service for admins

Templates
  ├── my_connections.html — already exists upstream ✓
  ├── settings.html — add self-service settings card
  └── index.html — add self_service_enabled checkbox to server edit modal

Translations
  └── fr.json, zh.json, fa.json — add admin self-service keys (en/ru already have them)
```

## Components

### 1. connection_service.py (new file)

Copied from local repo with **no changes** — already follows the injection pattern (never imports app).

**Key features:**
- `SelfServiceError` / `RateLimitError` exceptions
- `DEFAULT_SELF_SERVICE_SETTINGS` constant
- `ConnectionService` class with:
  - `get_self_service_options(user_id, source)` — eligible servers/protocols, remaining quota
  - `create_user_connection(user_id, server_id, protocol, name, source)` — validation, SSH provisioning, rollback
  - `delete_user_connection(user_id, connection_id, source)` — only `created_by == 'self_service'`
- Rate limiting (in-memory, per `(source, user_id)`)
- Per `(server_id, protocol)` asyncio locks

**Supported protocols for self-service:** `awg`, `awg2` (configurable via `allowed_protocols`)

### 2. app.py changes

#### 2a. Imports (near top)
```python
from connection_service import (
    ConnectionService,
    DEFAULT_SELF_SERVICE_SETTINGS,
    SelfServiceError,
    RateLimitError,
)
```

#### 2b. Pydantic models (near other models)
```python
class SelfServiceSettings(BaseModel):
    enabled: bool = False
    web_enabled: bool = True
    telegram_enabled: bool = True
    max_connections_per_user: int = 5
    rate_limit_count: int = 3
    rate_limit_window_seconds: int = 60
    allowed_protocols: List[str] = ['awg', 'awg2']

class SelfServiceConnectionRequest(BaseModel):
    server_id: int
    protocol: str = 'awg'
    name: str = 'VPN Connection'
```

- `EditServerRequest` → add `self_service_enabled: Optional[bool] = None`
- `SaveSettingsRequest` → add `self_service: SelfServiceSettings = SelfServiceSettings()`

#### 2c. load_data() migration (after `auto_backup` defaults)
```python
self_service = data['settings'].setdefault('self_service', dict(DEFAULT_SELF_SERVICE_SETTINGS))
for key, value in DEFAULT_SELF_SERVICE_SETTINGS.items():
    self_service.setdefault(key, value)
for server in data.get('servers', []):
    server.setdefault('self_service_enabled', False)
```

#### 2d. Instantiate ConnectionService (after helper functions, before routes)
```python
self_service_connections = ConnectionService(
    load_data=load_data,
    save_data=save_data,
    data_lock=DATA_LOCK,
    get_ssh=get_ssh,
    get_protocol_manager=get_protocol_manager,
    manager_call=_manager_call,
    generate_vpn_link=generate_vpn_link,
)
```

#### 2e. New API routes
| Method | Path | Handler | Tag |
|---|---|---|---|
| `GET` | `/api/my/connections/options` | `api_my_connection_options` | Self-service |
| `POST` | `/api/my/connections/add` | `api_my_connection_add` | Self-service |
| `POST` | `/api/my/connections/{id}/delete` | `api_my_connection_delete` | Self-service |

**Existing routes to KEEP as-is:**
- `GET /my` — renders my_connections.html (identical in both repos)
- `GET /api/my/connections` — lists user's connections (useful for frontend)
- `POST /api/my/connections/{id}/config` — fetches config (identical in both repos)

#### 2f. Modified existing routes
- `POST /api/servers/{id}/edit` — handle `self_service_enabled` field
- `POST /api/settings/save` — save `self_service` object to `data['settings']['self_service']`

#### 2g. launch_bot call (3 call sites)
```python
tg_bot.launch_bot(token, load_data, generate_vpn_link, save_data, self_service_svc=self_service_connections)
```

### 3. telegram_bot.py changes

#### 3a. launch_bot signature
```python
def launch_bot(token, load_data, generate_vpn_link, save_data=None, self_service_svc=None):
```

#### 3b. Self-service helper functions
- `_self_service_is_enabled(data)` — checks `settings.self_service.enabled`
- `_self_service_telegram_enabled(data)` — checks enabled + telegram_enabled
- `_get_eligible_servers(data)` — filters by self_service_enabled, allowed protocols, installed protocols

#### 3c. Callback routing in `_dispatch`
- `user_create` → show server list
- `user_create_server` → show protocol options
- `user_create_protocol` → prompt for device name
- `user_add_client` → create connection
- `user_delete` → confirmation
- `user_delete_confirm` → call service.delete

#### 3d. Security
- Block self-service for admins
- Resolve user fresh from `telegramId` on every callback

### 4. Template changes

#### 4a. settings.html
Add collapsible self-service settings card with:
- `enabled` toggle (master switch)
- `web_enabled` checkbox
- `telegram_enabled` checkbox
- `max_connections_per_user` number input
- `rate_limit_count` + `rate_limit_window_seconds` inputs
- `allowed_protocols` multi-select

#### 4b. index.html (server list)
Add `self_service_enabled` checkbox to server edit modal.

#### 4c. my_connections.html
Already exists upstream with config modal, VPN link, QR code tabs. May need minor additions for self-service create/delete UI and `created_by` badges.

### 5. Translations

Add to `fr.json`, `zh.json`, `fa.json`:
- `self_service_title`, `self_service_enabled`, `self_service_enabled_desc`
- `self_service_web`, `self_service_telegram`
- `self_service_max_conns`, `self_service_rate_limit`, `self_service_rate_window`
- `self_service_protocols`
- `server_self_service_enabled`, `server_self_service_enabled_desc`
- `self_service_disabled`, `no_servers_available`
- `create_connection`, `delete_connection`, `delete_connection_confirm`, `connections_counter`, `device_name`, `connection_deleted`

## Data model

### `settings.self_service` (new dict)
| Field | Type | Default |
|---|---|---|
| `enabled` | bool | False |
| `web_enabled` | bool | True |
| `telegram_enabled` | bool | True |
| `max_connections_per_user` | int | 5 |
| `rate_limit_count` | int | 3 |
| `rate_limit_window_seconds` | int | 60 |
| `allowed_protocols` | list | `['awg', 'awg2']` |

### Per-server field
| Field | Type | Default |
|---|---|---|
| `self_service_enabled` | bool | False |

### `user_connections` entries (already exist, enhanced)
| Field | Type | Notes |
|---|---|---|
| `created_by` | str | `'self_service'` or `'admin'` |
| `created_source` | str | `'web'` or `'telegram'` |
| `last_bytes` | int | Added during background sync |

## Error handling

- `RateLimitError` → HTTP 429
- `SelfServiceError` → HTTP status from exception (400, 403, 404)
- Unexpected exceptions → HTTP 500

## Testing

- `tests/test_connection_service.py` — 18 test cases (unit tests for ConnectionService)
- `tests/test_telegram_self_service.py` — Telegram self-service flow tests
- Run with: `python3 -m unittest tests.test_connection_service tests.test_telegram_self_service`

## Trade-offs considered

1. **Full replacement of existing /api/my/ routes** — rejected. Upstream routes are functional and serve different needs (listing vs. creating). Keep upstream routes, add new ones alongside.
2. **Backend-only (no UI)** — rejected per user request. Full self-service including UI and Telegram wizard.
3. **Import-based vs injection-based** — injection chosen to maintain circular-import safety (connection_service.py must never import app).

## Implementation order (commits)

1. `connection_service.py` + tests
2. app.py: imports, models, load_data migration, instantiation
3. app.py: new /api/my/ routes + modified /api/servers/{id}/edit + /api/settings/save
4. app.py: update launch_bot calls
5. telegram_bot.py: self-service integration
6. Templates: settings.html + index.html + my_connections.html
7. Translations: fr/zh/fa self-service keys
8. Tests: run full suite
