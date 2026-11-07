# Environment Configuration Specification (`app/config.py`)

## 1. Overview & Purpose

OryxGate relies on environment variables for external service integration credentials, database connections, and downstream consumer authentication tokens. The configuration layer is implemented using `pydantic-settings` to guarantee:

- **Fail-Fast Startup:** Mandatory settings are validated at process initialization. If any required configuration is missing or malformed, startup halts immediately with descriptive validation errors.
- **Zero Secret Leakage:** Sensitive parameters (API keys, passwords, bearer tokens) use Pydantic's `SecretStr` to ensure values are masked in `str()`, `repr()`, logs, and tracebacks.
- **Flexible Ingestion:** Supports loading from `.env` files and system environment variables with support for both JSON and comma-delimited strings for list fields.

---

## 2. Configuration Schema & Variables

| Variable Name        | Type              | Mandatory | Default         | Secret Masked | Description                                                                                                                   |
| :------------------- | :---------------- | :-------- | :-------------- | :------------ | :---------------------------------------------------------------------------------------------------------------------------- |
| `GATEWAY_API_TOKENS` | `list[SecretStr]` | **Yes**   | _None_          | **Yes**       | Comma-delimited or JSON array of Bearer tokens permitted to access OryxGate REST endpoints.                                   |
| `ADMIN_API_TOKENS`   | `list[SecretStr]` | **Yes**   | _None_          | **Yes**       | Comma-delimited or JSON array of privileged Bearer tokens permitted to access administrative routes and `force_refresh=true`. |
| `IF_API_KEY`         | `SecretStr`       | **Yes**   | _None_          | **Yes**       | Infinite Flight Live API v2 user key (passed via `?apikey=`).                                                                 |
| `IF_ORGANIZATION_ID` | `str`             | **Yes**   | _None_          | No            | Infinite Flight Live API v3 organization UUID.                                                                                |
| `CC_API_KEY`         | `SecretStr`       | **Yes**   | _None_          | **Yes**       | Crew Center PHP API secret key.                                                                                               |
| `CC_API_BASE_URL`    | `str`             | **Yes**   | _None_          | No            | Base HTTP/HTTPS URL for the Crew Center API (e.g. `https://crew.qatarairwaysvirtual.com/api`). Trailing slashes are stripped. |
| `DB_HOST`            | `str`             | **Yes**   | _None_          | No            | MySQL database hostname or IP address.                                                                                        |
| `DB_PORT`            | `int`             | No        | `3306`          | No            | MySQL database connection port.                                                                                               |
| `DB_USER`            | `str`             | **Yes**   | _None_          | No            | MySQL database user.                                                                                                          |
| `DB_PASSWORD`        | `SecretStr`       | **Yes**   | _None_          | **Yes**       | MySQL database user password.                                                                                                 |
| `DB_NAME`            | `str`             | **Yes**   | _None_          | No            | MySQL database schema name.                                                                                                   |
| `ENVIRONMENT`        | `str`             | No        | `"development"` | No            | Deployment environment (`development`, `staging`, `production`, `testing`).                                                   |
| `DEBUG`              | `bool`            | No        | `False`         | No            | Verbose debugging and reload flag.                                                                                            |
| `HOST`               | `str`             | No        | `"0.0.0.0"`     | No            | Server listen address for Uvicorn.                                                                                            |
| `PORT`               | `int`             | No        | `8000`          | No            | Server listen port for Uvicorn.                                                                                               |

### Caching TTL Defaults (Seconds)

| Variable Name         | Type  | Default | Description                                                |
| :-------------------- | :---- | :------ | :--------------------------------------------------------- |
| `CACHE_TTL_SESSIONS`  | `int` | `600`   | Infinite Flight v2 session list TTL (10 minutes)           |
| `CACHE_TTL_FLIGHTS`   | `int` | `20`    | Infinite Flight v2 active flights TTL (20 seconds)         |
| `CACHE_TTL_ROUTE`     | `int` | `60`    | Infinite Flight v2 route breadcrumbs TTL (60 seconds)      |
| `CACHE_TTL_ROSTER`    | `int` | `300`   | Infinite Flight v3 aircraft roster TTL (5 minutes)         |
| `CACHE_TTL_POSITIONS` | `int` | `30`    | Infinite Flight v3 aircraft positions TTL (30 seconds)     |
| `CACHE_TTL_SCHEDULES` | `int` | `60`    | Infinite Flight v3 organization schedules TTL (60 seconds) |

---

## 3. Ingestion & Validation Rules

1. **Token Ingestion Flexibility & Strict Parsing:**
   `GATEWAY_API_TOKENS` and `ADMIN_API_TOKENS` accept:
   - Comma-delimited strings: `"token1,token2, token3"`
   - JSON arrays of strings: `'["token1", "token2"]'`
   - Native sequences (`list`, `set`, `tuple`) of strings or `SecretStr`.
     Whitespace around individual tokens is trimmed. Empty token elements are discarded.
     If a bracketed token list is provided (`[...]`) but is not valid JSON (e.g. malformed syntax, trailing commas, or non-array JSON), validation fails fast with a descriptive `ValidationError` rather than silently falling back to comma-splitting.
     All elements within JSON arrays or native iterables must be strings or `SecretStr` instances; non-string elements (such as `null`, booleans, numbers, or objects) are strictly rejected with a `ValidationError` rather than coerced to strings, preventing guessable token generation.
     Mappings (such as `dict`) and non-sequence scalars are strictly rejected to prevent unintended credential creation from dictionary keys.
2. **Mandatory Non-Empty Gateway Tokens:**
   At least one non-empty gateway token is mandatory. Providing an empty list or blank string raises `ValidationError`.
3. **URL Normalization:**
   `CC_API_BASE_URL` validates HTTP/HTTPS schema and strips trailing slashes to prevent malformed endpoint concatenation (`//pireps`).
4. **Secret Masking & Zero-Leak Validation:**
   All secret fields (`GATEWAY_API_TOKENS`, `ADMIN_API_TOKENS`, `IF_API_KEY`, `CC_API_KEY`, `DB_PASSWORD`) must never output unmasked text in `__repr__`, `__str__`, logs, or Pydantic serialization.
   Furthermore, validation and parsing error messages for secret fields (including token list JSON decode errors) must never interpolate raw input strings or chain unmasked exception contexts, guaranteeing credentials in malformed payloads are never leaked into error messages or tracebacks.
5. **Case-Insensitive Environment Lookup & Attribute Access:**
   Variables can be populated from uppercase or lowercase environment keys. Attribute access on `Settings` instances supports both lowercase (`settings.db_host`) and uppercase (`settings.DB_HOST`) naming conventions.

---

## 4. Factory & Dependency Injection

Settings instances are accessed via the cached dependency provider `get_settings()`:

```python
from functools import lru_cache
from app.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

In test suites, calling `get_settings.cache_clear()` allows resetting or overriding settings deterministically.

---

## 5. Sample `.env.example`

```env
# Gateway Authentication
GATEWAY_API_TOKENS=gw_bot_secret_token,gw_webapp_secret_token
ADMIN_API_TOKENS=gw_admin_secret_token

# Infinite Flight Upstream
IF_API_KEY=if_live_v2_api_key_here
IF_ORGANIZATION_ID=00000000-0000-0000-0000-000000000000

# Crew Center Upstream
CC_API_KEY=crew_center_api_key_here
CC_API_BASE_URL=https://crew.qatarairwaysvirtual.com/api

# MySQL Database
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=oryxgate_user
DB_PASSWORD=oryxgate_secure_password
DB_NAME=oryxgate_db

# Runtime
ENVIRONMENT=development
DEBUG=false
HOST=0.0.0.0
PORT=8000
```
