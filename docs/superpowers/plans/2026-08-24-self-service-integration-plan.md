# Self-Service Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the complete self-service feature from the local repository into the upstream PRVTPRO/Amnezia-Web-Panel repository, adding user-facing connection creation/deletion via web UI and Telegram bot.

**Architecture:** ConnectionService is a standalone module (no `import app`) that receives dependencies via injection. It adds 3 new API routes, modifies 2 existing routes, enhances the Telegram bot with self-service wizard flows, and adds admin settings controls.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, asyncio, Jinja2 templates, raw Telegram Bot API via httpx, unittest.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `connection_service.py` | Create | Core self-service business logic |
| `tests/test_connection_service.py` | Create | Unit tests for ConnectionService |
| `tests/test_telegram_self_service.py` | Create | Unit tests for Telegram self-service flows |
| `app.py` | Modify | Imports, models, load_data migration, routes, instantiation |
| `telegram_bot.py` | Modify | launch_bot signature, self-service callbacks, i18n |
| `templates/my_connections.html` | Modify | Create/delete self-service UI |
| `templates/settings.html` | Modify | Self-service admin settings card |
| `templates/index.html` | Modify | Per-server self_service_enabled checkbox |
| `translations/fr.json` | Modify | Add self-service translation keys |
| `translations/zh.json` | Modify | Add self-service translation keys |
| `translations/fa.json` | Modify | Add self-service translation keys |

---

### Task 1: connection_service.py — Core module

**Files:**
- Create: `connection_service.py`

- [ ] **Step 1: Write connection_service.py**

Create `connection_service.py` with the following content:

```python
import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime

MAX_CONNECTION_NAME_LENGTH = 64

logger = logging.getLogger(__name__)


DEFAULT_SELF_SERVICE_SETTINGS = {
    'enabled': False,
    'web_enabled': True,
    'telegram_enabled': True,
    'max_connections_per_user': 5,
    'rate_limit_count': 3,
    'rate_limit_window_seconds': 60,
    'allowed_protocols': ['awg', 'awg2'],
}


class SelfServiceError(Exception):
    def __init__(self, message, status_code=400, forbidden=False):
        super().__init__(message)
        self.status_code = status_code
        self.forbidden = forbidden


class RateLimitError(SelfServiceError):
    def __init__(self, message='Rate limit exceeded'):
        super().__init__(message, status_code=429)


class ConnectionService:
    def __init__(
        self,
        *,
        load_data,
        save_data,
        data_lock,
        get_ssh,
        get_protocol_manager,
        manager_call,
        generate_vpn_link,
    ):
        self.load_data = load_data
        self.save_data = save_data
        self.data_lock = data_lock
        self.get_ssh = get_ssh
        self.get_protocol_manager = get_protocol_manager
        self.manager_call = manager_call
        self.generate_vpn_link = generate_vpn_link
        self._provision_locks = defaultdict(asyncio.Lock)
        self._rate_events = defaultdict(list)

    async def get_self_service_options(self, user_id, source):
        data = self.load_data()
        settings = self._settings(data)
        user = self._get_eligible_user(data, user_id)
        self._validate_channel(settings, source)
        user_connections = self._user_connections(data, user['id'])
        max_connections = int(settings.get('max_connections_per_user', 5))
        remaining = max(0, max_connections - len(user_connections))
        allowed_protocols = set(settings.get('allowed_protocols') or []) & {'awg', 'awg2'}
        servers = []
        for server_id, server in enumerate(data.get('servers', [])):
            if not server.get('self_service_enabled', False):
                continue
            protocols = []
            for protocol in ('awg', 'awg2'):
                if protocol in allowed_protocols and protocol in server.get('protocols', {}):
                    protocols.append({'protocol': protocol, 'name': self._protocol_name(protocol)})
            if protocols:
                servers.append({
                    'id': server_id,
                    'name': server.get('name') or server.get('host') or f'Server {server_id}',
                    'protocols': protocols,
                })
        return {
            'enabled': True,
            'max_connections_per_user': max_connections,
            'remaining_connections': remaining,
            'servers': servers,
        }

    async def create_user_connection(self, user_id, server_id, protocol, name, source):
        clean_name = self._validate_name(name)
        self._validate_protocol(protocol)
        data = self.load_data()
        settings = self._settings(data)
        self._validate_create_request(data, settings, user_id, server_id, protocol, clean_name, source)
        self._check_rate_limit(user_id, source, settings)

        lock = self._provision_locks[(server_id, protocol)]
        async with lock:
            async with self.data_lock:
                data = self.load_data()
                settings = self._settings(data)
                self._validate_create_request(data, settings, user_id, server_id, protocol, clean_name, source)
                self._check_rate_limit(user_id, source, settings)
                server = data['servers'][server_id]
                port = server.get('protocols', {}).get(protocol, {}).get('port', '55424')
                ssh = self.get_ssh(server)
                remote_client_id = None
                manager = None
                try:
                    await asyncio.to_thread(ssh.connect)
                    manager = self.get_protocol_manager(ssh, protocol)
                    result = await asyncio.to_thread(
                        self.manager_call,
                        manager,
                        'add_client',
                        protocol,
                        clean_name,
                        server.get('host', ''),
                        port,
                    )
                    remote_client_id = result.get('client_id')
                    if not remote_client_id:
                        raise RuntimeError('Remote client creation did not return client_id')
                    conn = {
                        'id': str(uuid.uuid4()),
                        'user_id': user['id'],
                        'server_id': server_id,
                        'protocol': protocol,
                        'client_id': remote_client_id,
                        'name': clean_name,
                        'created_at': datetime.now().isoformat(),
                        'created_by': 'self_service',
                        'created_source': source,
                    }
                    data.setdefault('user_connections', []).append(conn)
                    try:
                        self.save_data(data)
                    except Exception:
                        await self._rollback_client(manager, protocol, remote_client_id)
                        remote_client_id = None
                        raise
                    self._record_rate_event(user_id, source)
                    response = {'status': 'success', 'connection': conn}
                    if result.get('config'):
                        response['config'] = result['config']
                        response['vpn_link'] = self.generate_vpn_link(result['config'])
                    return response
                except Exception:
                    if remote_client_id:
                        await self._rollback_client(manager, protocol, remote_client_id)
                    raise
                finally:
                    try:
                        await asyncio.to_thread(ssh.disconnect)
                    except Exception:
                        pass

    async def delete_user_connection(self, user_id, connection_id, source):
        data = self.load_data()
        settings = self._settings(data)
        self._validate_channel(settings, source)
        self._get_eligible_user(data, user_id)
        conn = self._get_connection(data, user_id, connection_id)
        if conn.get('created_by') != 'self_service':
            raise SelfServiceError('Only self-service connections can be deleted', status_code=403, forbidden=True)
        server_id = conn.get('server_id')
        protocol = conn.get('protocol')
        lock = self._provision_locks[(server_id, protocol)]
        async with lock:
            async with self.data_lock:
                data = self.load_data()
                self._validate_channel(self._settings(data), source)
                self._get_eligible_user(data, user_id)
                conn = self._get_connection(data, user_id, connection_id)
                if conn.get('created_by') != 'self_service':
                    raise SelfServiceError('Only self-service connections can be deleted', status_code=403, forbidden=True)
                if server_id is None or server_id >= len(data.get('servers', [])):
                    raise SelfServiceError('Server not found', status_code=404)
                server = data['servers'][server_id]
                ssh = self.get_ssh(server)
                try:
                    await asyncio.to_thread(ssh.connect)
                    manager = self.get_protocol_manager(ssh, protocol)
                    await asyncio.to_thread(self.manager_call, manager, 'remove_client', protocol, conn.get('client_id'))
                    data['user_connections'] = [c for c in data.get('user_connections', []) if c.get('id') != connection_id]
                    self.save_data(data)
                    return {'status': 'success'}
                finally:
                    try:
                        await asyncio.to_thread(ssh.disconnect)
                    except Exception:
                        pass

    def _settings(self, data):
        settings = dict(DEFAULT_SELF_SERVICE_SETTINGS)
        settings.update(data.get('settings', {}).get('self_service') or {})
        return settings

    def _validate_channel(self, settings, source):
        if not settings.get('enabled', False):
            raise SelfServiceError('Self-service is disabled', status_code=403, forbidden=True)
        if source == 'web' and not settings.get('web_enabled', True):
            raise SelfServiceError('Web self-service is disabled', status_code=403, forbidden=True)
        if source == 'telegram' and not settings.get('telegram_enabled', True):
            raise SelfServiceError('Telegram self-service is disabled', status_code=403, forbidden=True)

    def _get_eligible_user(self, data, user_id):
        user = next((u for u in data.get('users', []) if u.get('id') == user_id), None)
        if not user:
            raise SelfServiceError('User not found', status_code=404)
        if not user.get('enabled', True):
            raise SelfServiceError('User is disabled', status_code=403, forbidden=True)
        expiration = user.get('expiration_date')
        if expiration:
            try:
                expires_at = datetime.fromisoformat(str(expiration).replace('Z', '+00:00'))
                now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
                if expires_at < now:
                    raise SelfServiceError('User is expired', status_code=403, forbidden=True)
            except SelfServiceError:
                raise
            except Exception as e:
                logger.warning("Failed to parse expiration_date '%s': %s", expiration, e)
        limit = int(user.get('traffic_limit') or 0)
        used = int(user.get('traffic_used') or 0)
        if limit > 0 and used >= limit:
            raise SelfServiceError('User quota is exhausted', status_code=403, forbidden=True)
        return user

    def _validate_create_request(self, data, settings, user_id, server_id, protocol, name, source):
        self._validate_channel(settings, source)
        user = self._get_eligible_user(data, user_id)
        user_connections = self._user_connections(data, user_id)
        max_connections = int(settings.get('max_connections_per_user', 5))
        if len(user_connections) >= max_connections:
            raise SelfServiceError('Maximum self-service connections reached', status_code=403, forbidden=True)
        if any(c.get('name') == name for c in user_connections):
            raise SelfServiceError('Connection name must be unique for this user')
        if server_id is None or server_id < 0 or server_id >= len(data.get('servers', [])):
            raise SelfServiceError('Server not found', status_code=404)
        server = data['servers'][server_id]
        if not server.get('self_service_enabled', False):
            raise SelfServiceError('Server self-service is disabled', status_code=403, forbidden=True)
        allowed = set(settings.get('allowed_protocols') or []) & {'awg', 'awg2'}
        if protocol not in allowed:
            raise SelfServiceError('Protocol is not allowed')
        if protocol not in server.get('protocols', {}):
            raise SelfServiceError('Protocol is not installed on this server')
        return user

    def _validate_name(self, name):
        clean = str(name or '').strip()
        if not clean or len(clean) > MAX_CONNECTION_NAME_LENGTH or any(ord(ch) < 32 or ord(ch) == 127 for ch in clean):
            raise SelfServiceError('Connection name must be 1-64 characters without control characters')
        return clean

    def _validate_protocol(self, protocol):
        if protocol not in ('awg', 'awg2'):
            raise SelfServiceError('Only awg and awg2 are supported')

    def _user_connections(self, data, user_id):
        return [c for c in data.get('user_connections', []) if c.get('user_id') == user_id]

    def _get_connection(self, data, user_id, connection_id):
        conn = next(
            (c for c in data.get('user_connections', []) if c.get('id') == connection_id and c.get('user_id') == user_id),
            None,
        )
        if not conn:
            raise SelfServiceError('Connection not found', status_code=404)
        return conn

    def _check_rate_limit(self, user_id, source, settings):
        count = int(settings.get('rate_limit_count', 3))
        window = int(settings.get('rate_limit_window_seconds', 60))
        if count <= 0 or window <= 0:
            return
        key = (source, user_id)
        now = time.monotonic()
        self._rate_events[key] = [ts for ts in self._rate_events[key] if now - ts < window]
        if len(self._rate_events[key]) >= count:
            raise RateLimitError()

    def _record_rate_event(self, user_id, source):
        self._rate_events[(source, user_id)].append(time.monotonic())

    async def _rollback_client(self, manager, protocol, client_id):
        try:
            await asyncio.to_thread(self.manager_call, manager, 'remove_client', protocol, client_id)
        except Exception as e:
            logger.warning("Rollback failed for client %s: %s", client_id, e)

    def _protocol_name(self, protocol):
        return 'AWG 2' if protocol == 'awg2' else 'AWG'
```

- [ ] **Step 2: Commit**

```bash
git add connection_service.py
git commit -m "feat: add ConnectionService for self-service VPN connections"
```

---

### Task 2: app.py — Imports, Pydantic models, load_data migration, ConnectionService instantiation

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add imports**

Insert after line 45 (`import telegram_bot as tg_bot`):

```python
from connection_service import (
    ConnectionService,
    DEFAULT_SELF_SERVICE_SETTINGS,
    RateLimitError,
    SelfServiceError,
)
```

- [ ] **Step 2: Add Pydantic models**

After the `TelegramSettings` model (line 1615), add:

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

- [ ] **Step 3: Modify EditServerRequest**

Add `self_service_enabled: Optional[bool] = None` to `EditServerRequest` (line 1461-1470):

```python
class EditServerRequest(BaseModel):
    name: str = ''
    host: str = ''
    ssh_port: int = 22
    username: str = ''
    # Optional[str] = None lets the client distinguish "leave field as is"
    # (omit / null) from "explicitly clear" (empty string). Both credential
    # fields can be omitted to keep current auth unchanged.
    password: Optional[str] = None
    private_key: Optional[str] = None
    self_service_enabled: Optional[bool] = None
```

- [ ] **Step 4: Modify SaveSettingsRequest**

Add `self_service: SelfServiceSettings = SelfServiceSettings()` to `SaveSettingsRequest` (around line 1647):

```python
class SaveSettingsRequest(BaseModel):
    appearance: AppearanceSettings
    sync: SyncSettings
    captcha: CaptchaSettings
    telegram: TelegramSettings
    ssl: SSLSettings
    self_service: SelfServiceSettings = SelfServiceSettings()
```

- [ ] **Step 5: Add self-service defaults in load_data()**

After the `auto_backup` setdefault block in `load_data()` (after `settings.setdefault('auto_backup', {...})` and before `return data`), add:

```python
    self_service = data['settings'].setdefault('self_service', dict(DEFAULT_SELF_SERVICE_SETTINGS))
    for key, value in DEFAULT_SELF_SERVICE_SETTINGS.items():
        self_service.setdefault(key, value)
    for server in data.get('servers', []):
        server.setdefault('self_service_enabled', False)
```

- [ ] **Step 6: Instantiate ConnectionService**

After `generate_vpn_link` function (around line 1027), add:

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

- [ ] **Step 7: Verify and commit**

Run: `python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"`

```bash
git add app.py
git commit -m "feat: add self-service models, defaults, and ConnectionService to app.py"
```

---

### Task 3: app.py — Self-service API routes

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add GET /api/my/connections/options**

After the existing `/api/my/connections` route (line ~3535), add:

```python
@app.get('/api/my/connections/options', tags=["Self-service"])
async def api_my_connection_options(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': 'Forbidden'}, status_code=403)
    try:
        return await self_service_connections.get_self_service_options(user['id'], 'web')
    except SelfServiceError as e:
        return JSONResponse({'error': str(e)}, status_code=e.status_code)
    except Exception as e:
        logger.exception("Error getting self-service options")
        return JSONResponse({'error': str(e)}, status_code=500)
```

- [ ] **Step 2: Add POST /api/my/connections/add**

After the `/api/my/connections/options` route, add:

```python
@app.post('/api/my/connections/add', tags=["Self-service"])
async def api_my_connection_add(request: Request, payload: SelfServiceConnectionRequest):
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': 'Forbidden'}, status_code=403)
    try:
        return await self_service_connections.create_user_connection(
            user['id'], payload.server_id, payload.protocol, payload.name, 'web'
        )
    except SelfServiceError as e:
        return JSONResponse({'error': str(e)}, status_code=e.status_code)
    except Exception as e:
        logger.exception("Error creating self-service connection")
        return JSONResponse({'error': str(e)}, status_code=500)
```

- [ ] **Step 3: Add POST /api/my/connections/{id}/delete**

After the `/api/my/connections/add` route, add:

```python
@app.post('/api/my/connections/{connection_id}/delete', tags=["Self-service"])
async def api_my_connection_delete(request: Request, connection_id: str):
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': 'Forbidden'}, status_code=403)
    try:
        return await self_service_connections.delete_user_connection(user['id'], connection_id, 'web')
    except SelfServiceError as e:
        return JSONResponse({'error': str(e)}, status_code=e.status_code)
    except Exception as e:
        logger.exception("Error deleting self-service connection")
        return JSONResponse({'error': str(e)}, status_code=500)
```

- [ ] **Step 4: Modify POST /api/servers/{server_id}/edit**

Find the `api_edit_server` handler. Add after `server['server_info'] = server_info` and before `save_data(data)`:

```python
        if req.self_service_enabled is not None:
            server['self_service_enabled'] = bool(req.self_service_enabled)
```

- [ ] **Step 5: Modify POST /api/settings/save**

Find the `save_settings` handler. Add after `data['settings']['ssl'] = payload.ssl.dict()` and before `save_data(data)`:

```python
    data['settings']['self_service'] = payload.self_service.dict()
```

Also update the `launch_bot` call at line ~3865 from:
```python
tg_bot.launch_bot(tg_cfg.token, load_data, generate_vpn_link, save_data)
```
to:
```python
tg_bot.launch_bot(tg_cfg.token, load_data, generate_vpn_link, save_data, self_service_svc=self_service_connections)
```

- [ ] **Step 6: Update all launch_bot calls**

There are 3 call sites. Update each to pass `self_service_svc=self_service_connections`:

1. In `lifespan()` function (around line 1770):
```python
tg_bot.launch_bot(tg_cfg['token'], load_data, generate_vpn_link, save_data, self_service_svc=self_service_connections)
```

2. In `api_telegram_toggle()` function (around line 3892):
```python
tg_bot.launch_bot(token, load_data, generate_vpn_link, save_data, self_service_svc=self_service_connections)
```

- [ ] **Step 7: Verify and commit**

Run: `python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"`

```bash
git add app.py
git commit -m "feat: add self-service API routes and update existing handlers"
```

---

### Task 4: telegram_bot.py — Self-service integration

**Files:**
- Modify: `telegram_bot.py`

- [ ] **Step 1: Update launch_bot signature**

Change the `launch_bot` function signature from:
```python
def launch_bot(token: str, load_data_fn: Callable, generate_vpn_link_fn: Callable, save_data_fn: Optional[Callable] = None):
```
to:
```python
def launch_bot(token: str, load_data_fn: Callable, generate_vpn_link_fn: Callable, save_data_fn: Optional[Callable] = None, self_service_svc=None):
```

Update `_run_bot` function signature to accept and pass `self_service_svc`:
```python
async def _run_bot(token: str, load_data_fn: Callable, generate_vpn_link_fn: Callable, save_data_fn: Optional[Callable] = None, self_service_svc=None):
```

Update the `_dispatch` call in `_run_bot` to pass `self_service_svc`:
```python
await _dispatch(api, update, load_data_fn, generate_vpn_link_fn, save_data_fn, self_service_svc=self_service_svc)
```

- [ ] **Step 2: Update _dispatch signature**

Change:
```python
async def _dispatch(api: TelegramAPI, update: dict, load_data_fn: Callable, generate_vpn_link_fn: Callable, save_data_fn: Optional[Callable] = None):
```
to:
```python
async def _dispatch(api: TelegramAPI, update: dict, load_data_fn: Callable, generate_vpn_link_fn: Callable, save_data_fn: Optional[Callable] = None, self_service_svc=None):
```

- [ ] **Step 3: Add self-service helper functions**

Before `_handle_start`, add:

```python
def _self_service_is_enabled(data: dict) -> bool:
    ss = data.get('settings', {}).get('self_service', {})
    return bool(ss.get('enabled', False))


def _self_service_telegram_enabled(data: dict) -> bool:
    ss = data.get('settings', {}).get('self_service', {})
    return bool(ss.get('enabled', False)) and bool(ss.get('telegram_enabled', True))


def _get_eligible_servers(data: dict, allowed_protocols: set) -> list:
    result = []
    for server_id, server in enumerate(data.get('servers', [])):
        if not server.get('self_service_enabled', False):
            continue
        protocols = []
        for proto in ('awg', 'awg2'):
            if proto in allowed_protocols and proto in server.get('protocols', {}):
                protocols.append({'protocol': proto, 'name': _protocol_display_name(proto)})
        if protocols:
            result.append({
                'id': server_id,
                'name': server.get('name') or server.get('host') or f'Server {server_id}',
                'protocols': protocols,
            })
    return result
```

- [ ] **Step 4: Add _find_user_by_username helper**

Update `_find_user` to accept an optional username parameter (from Telegram callback `from.username`):
```python
def _find_user(load_data_fn: Callable, tg_id: str, username: str = None):
    data = load_data_fn()
    tg_id_clean = str(tg_id).lstrip("@")
    for u in data.get("users", []):
        stored = str(u.get("telegramId", "") or "").lstrip("@")
        if stored and stored == tg_id_clean:
            return u
    if username:
        username_clean = str(username).lstrip("@")
        for u in data.get("users", []):
            stored = str(u.get("telegramId", "") or "").lstrip("@")
            if stored and stored == username_clean:
                return u
    return None
```

- [ ] **Step 5: Add self-service callback routing in _dispatch**

In `_dispatch`, after the `noop` / `refresh` / `cfg:` checks and before `panel_user = _require_admin(...)`, add:

```python
        # Self-service callbacks (non-admin users)
        if data_str.startswith("user_"):
            await _handle_self_service_callback(api, chat_id, message_id, callback_id, tg_id, data_str, load_data_fn, generate_vpn_link_fn, save_data_fn, self_service_svc, cq["from"].get("username"))
            return
```

- [ ] **Step 6: Add _handle_self_service_callback function**

Add this function before `_handle_start`:

```python
async def _handle_self_service_callback(api: TelegramAPI, chat_id: int, message_id: int, callback_id: str, tg_id: str, data_str: str, load_data_fn: Callable, generate_vpn_link_fn: Callable, save_data_fn: Optional[Callable], self_service_svc, tg_username: str = None):
    await api.answer_callback(callback_id)
    data = load_data_fn()

    panel_user = _find_user(load_data_fn, tg_id, tg_username)

    if not panel_user:
        await api.edit_message(chat_id, message_id, "❌ Access denied.")
        return

    if _is_admin(panel_user):
        return  # Admins use admin menu, not self-service

    if not _self_service_telegram_enabled(data):
        await api.edit_message(chat_id, message_id, "Self-service is not enabled. Please contact your administrator.")
        return

    if data_str == "user_create":
        await _user_create_start(api, chat_id, message_id, panel_user, data, load_data_fn)
    elif data_str == "user_create_cancel":
        await _user_create_cancel(api, chat_id, message_id, panel_user, data, load_data_fn)
    elif data_str.startswith("user_create_server"):
        ref = _resolve_ref(data_str)
        if not ref:
            await api.edit_message(chat_id, message_id, "❌ Action expired. Use /start again.")
            return
        await _user_create_server(api, chat_id, message_id, panel_user, ref.get("sid", 0), data, load_data_fn)
    elif data_str.startswith("user_create_protocol"):
        ref = _resolve_ref(data_str)
        if not ref:
            await api.edit_message(chat_id, message_id, "❌ Action expired. Use /start again.")
            return
        await _user_create_protocol(api, chat_id, message_id, panel_user, ref.get("sid", 0), ref.get("proto", ""), data, load_data_fn)
    elif data_str.startswith("user_add_client"):
        ref = _resolve_ref(data_str)
        if not ref:
            await api.edit_message(chat_id, message_id, "❌ Action expired. Use /start again.")
            return
        await _user_add_client_final(api, chat_id, message_id, panel_user, ref, load_data_fn, generate_vpn_link_fn, self_service_svc)
    elif data_str.startswith("user_delete"):
        ref = _resolve_ref(data_str)
        if not ref:
            await api.edit_message(chat_id, message_id, "❌ Action expired. Use /start again.")
            return
        await _user_delete(api, chat_id, message_id, panel_user, ref, load_data_fn, self_service_svc)
```

- [ ] **Step 7: Add self-service handler functions**

Add these functions after `_handle_start`:

```python
async def _user_create_start(api: TelegramAPI, chat_id: int, message_id: int, panel_user: dict, data: dict, load_data_fn: Callable):
    settings = data.get('settings', {}).get('self_service', {})
    allowed = set(settings.get('allowed_protocols') or []) & {'awg', 'awg2'}
    servers = _get_eligible_servers(data, allowed)
    user_connections = [c for c in data.get('user_connections', []) if c.get('user_id') == panel_user.get('id')]
    max_conns = int(settings.get('max_connections_per_user', 5))
    remaining = max(0, max_conns - len(user_connections))

    if not servers:
        await api.edit_message(chat_id, message_id, "No servers available for self-service. Please contact your administrator.")
        return

    rows = []
    for s in servers:
        rows.append([{"text": f"🖥 {s['name']}", "callback_data": _ref("user_create_server", {"sid": s['id']})}])
    rows.append([{"text": "❌ Cancel", "callback_data": "user_create_cancel"}])

    text = f"🔐 <b>Create connection</b>\n\n" \
           f"You can create <b>{remaining}</b> more connection(s).\n\n" \
           f"Choose a server:"

    await api.edit_message(chat_id, message_id, text, reply_markup={"inline_keyboard": rows})


async def _user_create_cancel(api: TelegramAPI, chat_id: int, message_id: int, panel_user: dict, data: dict, load_data_fn: Callable):
    _pending_inputs.pop(str(chat_id), None)
    await api.send_message(chat_id, "❌ Connection creation cancelled.")
    await _send_user_connections(api, chat_id, panel_user, load_data_fn)


async def _user_create_server(api: TelegramAPI, chat_id: int, message_id: int, panel_user: dict, server_id: int, data: dict, load_data_fn: Callable):
    server = data.get('servers', [])[server_id]
    settings = data.get('settings', {}).get('self_service', {})
    allowed = set(settings.get('allowed_protocols') or []) & {'awg', 'awg2'}
    protocols = []
    for proto in ('awg', 'awg2'):
        if proto in allowed and proto in server.get('protocols', {}):
            protocols.append({'protocol': proto, 'name': _protocol_display_name(proto)})

    rows = []
    for p in protocols:
        rows.append([{"text": f"🔌 {p['name']}", "callback_data": _ref("user_create_protocol", {"sid": server_id, "proto": p['protocol']})}])
    rows.append([{"text": "⬅️ Back", "callback_data": "user_create"}])

    text = f"🔐 <b>Create connection</b>\n\n" \
           f"Server: <b>{_e(server.get('name') or server.get('host'))}</b>\n\n" \
           f"Choose a protocol:"

    await api.edit_message(chat_id, message_id, text, reply_markup={"inline_keyboard": rows})


async def _user_create_protocol(api: TelegramAPI, chat_id: int, message_id: int, panel_user: dict, server_id: int, proto: str, data: dict, load_data_fn: Callable):
    server = data.get('servers', [])[server_id]
    _pending_inputs[str(chat_id)] = {
        'kind': 'user_add_client_name',
        'sid': server_id,
        'proto': proto,
        'ts': time.time(),
    }

    text = f"🔐 <b>Create connection</b>\n\n" \
           f"Server: <b>{_e(server.get('name') or server.get('host'))}</b>\n" \
           f"Protocol: <b>{_e(_protocol_display_name(proto))}</b>\n\n" \
           f"Send the device name in the next message.\n" \
           f"Example: <code>My iPhone</code>\n\n" \
           f"Send <code>/cancel</code> to cancel."

    await api.edit_message(chat_id, message_id, text, reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": "user_create_cancel"}]]})


async def _user_add_client_final(api: TelegramAPI, chat_id: int, message_id: int, panel_user: dict, ref: dict, load_data_fn: Callable, generate_vpn_link_fn: Callable, self_service_svc):
    if not self_service_svc:
        await api.edit_message(chat_id, message_id, "❌ Self-service is not available.")
        return

    sid = ref.get('sid')
    proto = ref.get('proto')
    name = ref.get('name')

    if not name or not name.strip():
        await api.edit_message(chat_id, message_id, "❌ Device name is required.")
        return

    await api.edit_message(chat_id, message_id, "⏳ Creating connection...")

    try:
        result = await self_service_svc.create_user_connection(panel_user['id'], sid, proto, name.strip(), 'telegram')
        if result.get('status') == 'success':
            await api.edit_message(chat_id, message_id, f"✅ Connection created: <b>{_e(name)}</b>")
            config = result.get('config')
            if config:
                await api.send_message(chat_id, f"<b>📄 Configuration:</b>\n<pre>{_e(config)}</pre>")
                vpn_link = result.get('vpn_link', '')
                if vpn_link:
                    await api.send_message(chat_id, f"🔗 <b>VPN Link</b>:\n<code>{_e(vpn_link)}</code>")
            await _send_user_connections(api, chat_id, panel_user, load_data_fn)
    except Exception as e:
        logger.exception("Bot: self-service creation failed")
        await api.edit_message(chat_id, message_id, f"❌ Error: {_e(e)}")


async def _user_delete(api: TelegramAPI, chat_id: int, message_id: int, panel_user: dict, ref: dict, load_data_fn: Callable, self_service_svc):
    conn_id = ref.get('conn_id')
    name = ref.get('name', 'Connection')
    action = ref.get('action', 'ask')

    if action == 'confirm':
        if not self_service_svc:
            await api.edit_message(chat_id, message_id, "❌ Self-service is not available.")
            return
        await api.edit_message(chat_id, message_id, f"🗑 <b>Delete connection</b>\n\n" \
            f"Are you sure you want to delete <b>{_e(name)}</b>? This cannot be undone.",
            reply_markup={"inline_keyboard": [
                [{"text": "✅ Yes, delete", "callback_data": _ref("user_delete", {"conn_id": conn_id, "action": "execute"})}],
                [{"text": "❌ Cancel", "callback_data": "user_create_cancel"}],
            ]})
    elif action == 'execute':
        await api.edit_message(chat_id, message_id, "⏳ Deleting connection...")
        try:
            await self_service_svc.delete_user_connection(panel_user['id'], conn_id, 'telegram')
            await api.edit_message(chat_id, message_id, f"✅ Connection <b>{_e(name)}</b> deleted.")
            await _send_user_connections(api, chat_id, panel_user, load_data_fn)
        except Exception as e:
            logger.exception("Bot: self-service deletion failed")
            await api.edit_message(chat_id, message_id, f"❌ Error: {_e(e)}")


def _build_connections_keyboard_user(conns: list, data: dict, ss_enabled: bool) -> dict:
    """Build inline keyboard for user connections with self-service delete buttons."""
    rows = []
    servers = data.get("servers", [])
    for c in conns:
        sid = c.get("server_id", 0)
        server_name = "Unknown"
        if isinstance(sid, int) and sid < len(servers):
            srv = servers[sid]
            server_name = srv.get("name") or srv.get("host", "Unknown")[:20]
        proto = c.get("protocol", "").upper()
        name = c.get("name", "Connection")
        label = f"🔐 {name} · {proto} · {server_name}"
        row = [{"text": label, "callback_data": f"cfg:{c['id']}"}]
        if c.get('created_by') == 'self_service':
            row.append({"text": "🗑", "callback_data": _ref("user_delete", {"conn_id": c['id'], "name": name, "action": "confirm"})})
        rows.append(row)
    rows.append([{"text": "🔄 Refresh list", "callback_data": "refresh"}])
    if ss_enabled:
        rows.append([{"text": "➕ Create connection", "callback_data": "user_create"}])
    return {"inline_keyboard": rows}
```

- [ ] **Step 8: Update _handle_pending_input signature and _run_bot call**

Change `_handle_pending_input` signature from:
```python
async def _handle_pending_input(api, msg, load_data_fn, save_data_fn, generate_vpn_link_fn) -> bool:
```
to:
```python
async def _handle_pending_input(api, msg, load_data_fn, save_data_fn, generate_vpn_link_fn, self_service_svc=None) -> bool:
```

Update the call in `_run_bot` from:
```python
if await _handle_pending_input(api, msg, load_data_fn, save_data_fn, generate_vpn_link_fn):
```
to:
```python
if await _handle_pending_input(api, msg, load_data_fn, save_data_fn, generate_vpn_link_fn, self_service_svc):
```

- [ ] **Step 9: Add user_add_client_name handling in _handle_pending_input**

In `_handle_pending_input`, find the existing `if state.get("kind") == "add_client_name":` block (admin flow) and add AFTER its entire `if/return True` block:

```python
    if state.get("kind") == "user_add_client_name":
        panel_user = _find_user(load_data_fn, str(msg["from"]["id"]), msg["from"].get("username"))
        if not panel_user or _is_admin(panel_user):
            _pending_inputs.pop(str(chat_id), None)
            await api.send_message(chat_id, "❌ Access denied.")
            return True
        name = text[:MAX_CONNECTION_NAME_LENGTH].strip()
        if not name:
            await api.send_message(chat_id, "Name cannot be empty. Send a device name or /cancel.")
            return True
        _pending_inputs.pop(str(chat_id), None)
        if not self_service_svc:
            await api.send_message(chat_id, "❌ Self-service is not available.")
            return True
        try:
            result = await self_service_svc.create_user_connection(
                panel_user["id"], state.get("sid"), state.get("proto"), name, "telegram"
            )
            if result.get("status") == "success":
                await api.send_message(chat_id, f"✅ Connection created: <b>{_e(name)}</b>")
                if result.get("config"):
                    await api.send_message(chat_id, f"<b>📄 Configuration:</b>\n<pre>{_e(result['config'])}</pre>")
                    if result.get("vpn_link"):
                        await api.send_message(chat_id, f"🔗 <b>VPN Link</b>:\n<code>{_e(result['vpn_link'])}</code>")
            await _send_user_connections(api, chat_id, panel_user, load_data_fn)
        except Exception as e:
            logger.exception("Bot: self-service creation from input failed")
            await api.send_message(chat_id, f"❌ Error: {_e(e)}")
        return True
```

- [ ] **Step 10: Update _send_user_connections to use new keyboard**

Modify `_send_user_connections` to use `_build_connections_keyboard_user` instead of `_build_connections_keyboard`, and add the "Create connection" button when self-service is enabled:

```python
async def _send_user_connections(api: TelegramAPI, chat_id: int, panel_user: dict, load_data_fn: Callable, first_name: str = ""):
    data = load_data_fn()
    conns = [c for c in data.get("user_connections", []) if c.get("user_id") == panel_user.get("id")]
    ss_enabled = _self_service_telegram_enabled(data)

    if not conns:
        greeting = f"👋 Hi, <b>{_e(first_name)}</b>!\n\n" if first_name else ""
        extra = f'\n\nYou can <b>create a new connection</b> using the button below.' if ss_enabled else '\n\nPlease contact your administrator.'
        kb = _build_connections_keyboard_user(conns, data, ss_enabled)
        await api.send_message(
            chat_id,
            greeting + f"You are registered as <b>{_e(panel_user.get('username'))}</b>.\n\n"
            f"You have no connections yet.{extra}",
            reply_markup=kb,
        )
        return

    kb = _build_connections_keyboard_user(conns, data, ss_enabled)
    greeting = f"👋 Hi, <b>{_e(first_name)}</b>!\n\n" if first_name else ""
    await api.send_message(
        chat_id,
        greeting + f"You are registered as <b>{_e(panel_user.get('username'))}</b>.\n\n"
        f"<b>Your connections</b> ({len(conns)}) — tap to get config:",
        reply_markup=kb,
    )
```

- [ ] **Step 11: Update _find_user calls in _dispatch to pass username**

In `_dispatch`, update the `_find_user` call for message handling to pass `msg["from"].get("username")`:

```python
        panel_user = _find_user(load_data_fn, tg_id, msg["from"].get("username"))
```

And for callback_query handling:
```python
        panel_user = _find_user(load_data_fn, tg_id, cq["from"].get("username"))
```

- [ ] **Step 12: Verify and commit**

Run: `python3 -c "import py_compile; py_compile.compile('telegram_bot.py', doraise=True)"`

```bash
git add telegram_bot.py
git commit -m "feat: add self-service Telegram bot integration"
```

---

### Task 5: Tests

**Files:**
- Create: `tests/test_connection_service.py`
- Create: `tests/test_telegram_self_service.py`

- [ ] **Step 1: Copy test_connection_service.py**

Copy from local repository — this file has 20 test cases for ConnectionService.

- [ ] **Step 2: Copy test_telegram_self_service.py**

Copy from local repository — this file has tests for Telegram self-service flows.

- [ ] **Step 3: Run tests**

```bash
python3 -m unittest tests.test_connection_service tests.test_telegram_self_service -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add self-service unit tests"
```

---

### Task 6: Templates — settings.html + index.html + my_connections.html

**Files:**
- Modify: `templates/settings.html`
- Modify: `templates/index.html`
- Modify: `templates/my_connections.html`

- [ ] **Step 1: settings.html — Add self-service card**

In `templates/settings.html`, find the appearance/settings sections and add after them:

```html
<!-- Self-Service Settings -->
<div class="card" style="margin-bottom: var(--space-lg);">
    <div class="card-header" onclick="toggleSection('selfServiceSection')" style="cursor:pointer;">
        <h3>🔐 {{ _('self_service_title') }}</h3>
    </div>
    <div id="selfServiceSection" class="card-body">
        <div class="form-group">
            <label class="form-label">
                <input type="checkbox" id="ssEnabled"> {{ _('self_service_enabled') }}
            </label>
            <p class="form-hint">{{ _('self_service_enabled_desc') }}</p>
        </div>
        <div id="ssSubFields" class="hidden">
            <div class="form-group">
                <label class="form-label">
                    <input type="checkbox" id="ssWebEnabled"> {{ _('self_service_web') }}
                </label>
            </div>
            <div class="form-group">
                <label class="form-label">
                    <input type="checkbox" id="ssTelegramEnabled"> {{ _('self_service_telegram') }}
                </label>
            </div>
            <div class="form-group">
                <label class="form-label">{{ _('self_service_max_conns') }}</label>
                <input type="number" class="form-input" id="ssMaxConnections" min="1" max="50" value="5">
            </div>
            <div class="form-group">
                <label class="form-label">{{ _('self_service_rate_limit') }}</label>
                <input type="number" class="form-input" id="ssRateLimit" min="1" max="100" value="3">
            </div>
            <div class="form-group">
                <label class="form-label">{{ _('self_service_rate_window') }}</label>
                <input type="number" class="form-input" id="ssRateWindow" min="10" max="3600" value="60">
            </div>
            <div class="form-group">
                <label class="form-label">{{ _('self_service_protocols') }}</label>
                <div class="flex gap-md">
                    <label><input type="checkbox" id="ssProtoAwg" checked> AWG</label>
                    <label><input type="checkbox" id="ssProtoAwg2"> AWG 2.0</label>
                </div>
            </div>
        </div>
    </div>
</div>
```

Add JavaScript to collect self-service settings in the existing `saveSettings()` function:

```javascript
// In saveSettings(), add to the payload object:
self_service: {
    enabled: document.getElementById('ssEnabled').checked,
    web_enabled: document.getElementById('ssWebEnabled').checked,
    telegram_enabled: document.getElementById('ssTelegramEnabled').checked,
    max_connections_per_user: parseInt(document.getElementById('ssMaxConnections').value) || 5,
    rate_limit_count: parseInt(document.getElementById('ssRateLimit').value) || 3,
    rate_limit_window_seconds: parseInt(document.getElementById('ssRateWindow').value) || 60,
    allowed_protocols: [
        ...(document.getElementById('ssProtoAwg').checked ? ['awg'] : []),
        ...(document.getElementById('ssProtoAwg2').checked ? ['awg2'] : []),
    ],
},
```

Add JavaScript to toggle sub-fields visibility:

```javascript
function toggleSection(id) {
    const el = document.getElementById(id);
    el.classList.toggle('hidden');
}

document.getElementById('ssEnabled')?.addEventListener('change', function() {
    document.getElementById('ssSubFields').classList.toggle('hidden', !this.checked);
});

// Load existing settings on page load:
function loadSelfServiceSettings() {
    const ss = window.settingsData?.self_service || {};
    document.getElementById('ssEnabled').checked = ss.enabled || false;
    document.getElementById('ssWebEnabled').checked = ss.web_enabled !== false;
    document.getElementById('ssTelegramEnabled').checked = ss.telegram_enabled !== false;
    document.getElementById('ssMaxConnections').value = ss.max_connections_per_user || 5;
    document.getElementById('ssRateLimit').value = ss.rate_limit_count || 3;
    document.getElementById('ssRateWindow').value = ss.rate_limit_window_seconds || 60;
    document.getElementById('ssProtoAwg').checked = (ss.allowed_protocols || ['awg']).includes('awg');
    document.getElementById('ssProtoAwg2').checked = (ss.allowed_protocols || []).includes('awg2');
    document.getElementById('ssSubFields').classList.toggle('hidden', !ss.enabled);
}
```

Call `loadSelfServiceSettings()` on page load.

- [ ] **Step 2: index.html — Add self_service_enabled checkbox to server edit modal**

In the server edit modal, add:

```html
<div class="form-group">
    <label class="form-label">
        <input type="checkbox" id="editServerSelfService"> {{ _('server_self_service_enabled') }}
    </label>
    <p class="form-hint">{{ _('server_self_service_enabled_desc') }}</p>
</div>
```

In the JavaScript that populates the edit modal:
```javascript
document.getElementById('editServerSelfService').checked = server.self_service_enabled || false;
```

In the submit handler:
```javascript
self_service_enabled: document.getElementById('editServerSelfService').checked,
```

- [ ] **Step 3: my_connections.html — Add create/delete UI**

The upstream already has `my_connections.html` with basic display. Enhance it to:
1. Show the "Create connection" button when self-service options are available
2. Show delete button only for `created_by == 'self_service'` connections
3. Show `self_service_disabled` message when self-service is disabled
4. Add the create connection modal with server/protocol/name form
5. Add JavaScript for `openCreateConnectionModal()`, `submitCreateConnection()`, `deleteConnection()`, `showMyConfig()`

- [ ] **Step 4: Commit**

```bash
git add templates/
git commit -m "feat: add self-service UI to settings, server edit, and my connections pages"
```

---

### Task 7: Translations — fr.json, zh.json, fa.json

**Files:**
- Modify: `translations/fr.json`
- Modify: `translations/zh.json`
- Modify: `translations/fa.json`

- [ ] **Step 1: Add to fr.json**

Add these keys to `translations/fr.json`:

```json
{
  "self_service_title": "Auto-service",
  "self_service_enabled": "Activer l'auto-service",
  "self_service_enabled_desc": "Permettre aux utilisateurs de créer et supprimer leurs propres connexions VPN",
  "self_service_web": "Auto-service via le site web",
  "self_service_telegram": "Auto-service via Telegram",
  "self_service_max_conns": "Connexions max par utilisateur",
  "self_service_rate_limit": "Limite de créations par fenêtre",
  "self_service_rate_window": "Fenêtre de limite (secondes)",
  "self_service_protocols": "Protocoles autorisés",
  "server_self_service_enabled": "Activer l'auto-service pour ce serveur",
  "server_self_service_enabled_desc": "Les utilisateurs peuvent créer des connexions sur ce serveur",
  "self_service_disabled": "L'auto-service est désactivé. Contactez votre administrateur.",
  "no_servers_available": "Aucun serveur disponible",
  "create_connection": "Créer une connexion",
  "delete_connection": "Supprimer",
  "delete_connection_confirm": "Supprimer cette connexion ? Cette action est irréversible.",
  "connections_counter": "Connexions",
  "device_name": "Nom de l'appareil",
  "connection_deleted": "Connexion supprimée"
}
```

- [ ] **Step 2: Add to zh.json**

```json
{
  "self_service_title": "自助服务",
  "self_service_enabled": "启用自助服务",
  "self_service_enabled_desc": "允许用户创建和删除自己的 VPN 连接",
  "self_service_web": "通过网站启用自助服务",
  "self_service_telegram": "通过 Telegram 启用自助服务",
  "self_service_max_conns": "每用户最大连接数",
  "self_service_rate_limit": "创建速率限制",
  "self_service_rate_window": "速率限制窗口（秒）",
  "self_service_protocols": "允许的协议",
  "server_self_service_enabled": "为此服务器启用自助服务",
  "server_self_service_enabled_desc": "用户可以在此服务器上创建连接",
  "self_service_disabled": "自助服务已禁用。请联系管理员。",
  "no_servers_available": "没有可用的服务器",
  "create_connection": "创建连接",
  "delete_connection": "删除",
  "delete_connection_confirm": "确定删除此连接？此操作不可撤销。",
  "connections_counter": "连接",
  "device_name": "设备名称",
  "connection_deleted": "连接已删除"
}
```

- [ ] **Step 3: Add to fa.json**

```json
{
  "self_service_title": "سرویس خودکار",
  "self_service_enabled": "فعال‌سازی سرویس خودکار",
  "self_service_enabled_desc": "اجازه به کاربران برای ایجاد و حذف اتصالات VPN خود",
  "self_service_web": "سرویس خودکار از طریق وب‌سایت",
  "self_service_telegram": "سرویس خودکار از طریق تلگرام",
  "self_service_max_conns": "حداکثر اتصال برای هر کاربر",
  "self_service_rate_limit": "محدودیت نرخ ایجاد",
  "self_service_rate_window": "پنجره محدودیت نرخ (ثانیه)",
  "self_service_protocols": "پروتکل‌های مجاز",
  "server_self_service_enabled": "فعال‌سازی سرویس خودکار برای این سرور",
  "server_self_service_enabled_desc": "کاربران می‌توانند اتصالات را روی این سرور ایجاد کنند",
  "self_service_disabled": "سرویس خودکار غیرفعال است. با مدیر تماس بگیرید.",
  "no_servers_available": "هیچ سروری موجود نیست",
  "create_connection": "ایجاد اتصال",
  "delete_connection": "حذف",
  "delete_connection_confirm": "این اتصال حذف شود؟ این عمل برگشت‌ناپذیر است.",
  "connections_counter": "اتصال",
  "device_name": "نام دستگاه",
  "connection_deleted": "اتصال حذف شد"
}
```

- [ ] **Step 4: Validate JSON**

```bash
python3 -c "import json; json.load(open('translations/fr.json'))"
python3 -c "import json; json.load(open('translations/zh.json'))"
python3 -c "import json; json.load(open('translations/fa.json'))"
```

- [ ] **Step 5: Commit**

```bash
git add translations/
git commit -m "i18n: add self-service translation keys for fr, zh, fa"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run all tests**

```bash
python3 -m unittest tests.test_connection_service tests.test_telegram_self_service -v
```

- [ ] **Step 2: Compile check**

```bash
python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('telegram_bot.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('connection_service.py', doraise=True)"
```

- [ ] **Step 3: Verify translation files are valid JSON**

```bash
python3 -c "
import json, os
for f in ['translations/en.json', 'translations/ru.json', 'translations/fr.json', 'translations/zh.json', 'translations/fa.json']:
    json.load(open(f))
    print(f'{f}: OK')
"
```

