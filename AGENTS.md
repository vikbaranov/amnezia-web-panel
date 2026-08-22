# AGENTS.md

## Run & verify

- Run the panel: `python3 app.py` → serves on `http://localhost:5000` (port comes from `settings.ssl.panel_port`). Default login `admin` / `admin`.
- Tests are plain `unittest` (no pytest installed). Run a single suite with:
  `python3 -m unittest tests.test_connection_service tests.test_telegram_self_service tests.test_awg_manager_ip_allocation`
- Tests import `telegram_bot`, which imports `httpx` — the `httpx` dependency must be installed or the telegram tests fail to import.
- There is **no lint/typecheck/test step in CI** (`.github/workflows/build.yml` only builds PyInstaller binaries on push to `main`/tags). Verify Python changes with `python3 -c "import py_compile; py_compile.compile('app.py', doraise=True)"` and the unittest suites.

## Architecture (single-process monolith)

- `app.py` is the FastAPI entrypoint and contains **all** routes (~4000 lines). Everything else is imported into it.
- `managers/` — one file per protocol (awg, xray, wireguard, telemt, dns, adguard, socks5, nginx, ssh, backup), each built on `ssh_manager.py` (Paramiko). SSH is the transport to remote Ubuntu servers.
- `telegram_bot.py` — uses the **raw Telegram Bot API via `httpx` long-polling**, NOT the `python-telegram-bot` package (it's in `requirements.txt` but unused). Do not introduce it.
- `connection_service.py` — shared self-service create/delete/options service.

### Circular-import rule (critical)

`telegram_bot.py` and `connection_service.py` must **never** `import app`. They receive dependencies by injection (`load_data`, `save_data`, `get_ssh`, `get_protocol_manager`, `_manager_call`, `generate_vpn_link`, `self_service_svc`). Wire new capabilities this way rather than reaching into `app`.

## Data & storage

- Single `data.json` file (gitignored) holds servers, users, connections, tokens, settings. Guarded by `asyncio.Lock` (`DATA_LOCK`).
- `load_data()` / `save_data()` are **synchronous** file I/O and are the source of truth; async paths should use `save_data_async()`. `load_data()` lazily applies defaults/migrations (`settings.self_service`, per-server `self_service_enabled`, etc.) — keep new defaults there.
- `settings.self_service` (enabled, `web_enabled`, `telegram_enabled`, `allowed_protocols`, limits) gates self-service; each server also has `self_service_enabled`.

## Conventions that differ from defaults

- **Protocol keys**: `base__instance` (e.g. `awg`, `awg2`, `awg_legacy`, `xray`, `telemt`); `awg2`/`awg_legacy` are distinct bases, not instances of `awg`. Helpers `protocol_base()`, `protocol_instance()`, `protocol_key()` live in `app.py`.
- **i18n**: 5 JSON files in `translations/` (`en`, `ru`, `fr`, `zh`, `fa`). Every new UI string needs a key in **all five** (Persian is RTL). Templates use `{{ _('key') }}`; Python uses `_t('key', lang)`.
- **Telegram security**: resolve the panel user from the sender's `telegramId` on *every* callback; never trust a `user_id` embedded in callback payloads.
- **Self-service ownership**: users may only delete connections with `created_by == "self_service"`; admin-created assignments are rejected by `connection_service`.
- **OpenAPI tag order** in `/docs` is driven by the `OPENAPI_TAGS` list at the top of `app.py`.

## Feature workflow

`docs/superpowers/` holds design specs and implementation plans (see the self-service example). Non-trivial features are specified and planned there before code changes.
