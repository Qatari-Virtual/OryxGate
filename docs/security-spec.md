# Gateway Bearer Authentication & Security Specification (`app/core/security.py`)

## 1. Overview & Purpose

OryxGate acts as a secure, high-throughput gateway protecting upstream services (Infinite Flight Live APIs, Crew Center, MySQL) from direct external exposure. Downstream callers—such as the Oryxie Discord Bot, WebApp backend servers, and internal automation workers—must authenticate using HTTP Bearer tokens.

This specification defines:
- The token validation algorithm and constant-time comparison to prevent timing attacks.
- Caller identity and assigned permission scopes (`read`, `write`, `admin`).
- FastAPI dependency injection interfaces (`get_current_token`, `require_admin`, `require_scope`).
- Error handling, HTTP status codes, and security response headers.

---

## 2. Authentication Protocol & Headers

### 2.1. Request Header
Downstream clients must provide a Bearer token via the standard HTTP `Authorization` header:
```http
Authorization: Bearer <GATEWAY_API_TOKEN>
```

### 2.2. Error Responses & Status Codes
- **`401 Unauthorized`**:
  - Missing `Authorization` header.
  - Malformed header (e.g. non-Bearer scheme, missing token).
  - Unrecognized or invalid token.
  - Every `401` response must include the HTTP header:
    ```http
    WWW-Authenticate: Bearer
    ```
- **`403 Forbidden`**:
  - Valid token provided, but caller context lacks the required scope (e.g. standard gateway token attempting an admin-scoped route or `force_refresh=true`).

---

## 3. Scopes & Caller Context

### 3.1. Token Classes & Scopes
Tokens are configured via environment variables and loaded through `app.config.Settings`:

| Token Category | Configuration Field | Default Assigned Scopes | Intended Consumers |
| :--- | :--- | :--- | :--- |
| **Standard Gateway** | `GATEWAY_API_TOKENS` | `read`, `write` | Oryxie Discord Bot, WebApp backend, standard automation |
| **Admin Gateway** | `ADMIN_API_TOKENS` | `read`, `write`, `admin` | Operations admins, cache invalidation, forced refresh (`force_refresh=true`) |

If a token is present in both configurations, it receives the union of scopes: `{"read", "write", "admin"}`.

### 3.2. Caller Context Domain Entity (`CallerContext`)
When authentication succeeds, `get_current_token` yields a `CallerContext` object:

```python
class CallerContext:
    token: str
    scopes: set[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.scopes

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
```

---

## 4. Security & Cryptographic Invariants

1. **Constant-Time Comparison:**
   All candidate tokens are evaluated against configured token pools using `secrets.compare_digest` to prevent side-channel timing attacks.
2. **Sub-Millisecond Verification:**
   Verification against in-memory token pools must complete in $< 1\text{ms}$ (typically $< 0.05\text{ms}$).
3. **No Secret Leakage:**
   Token values must never be logged or echoed in error payloads. When converted to string or logged, token values must be masked (e.g. `CallerContext` representations mask the raw token string).

---

## 5. FastAPI Dependency Signatures

### 5.1. `get_current_token`
```python
async def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    settings: Settings = Depends(get_settings),
) -> CallerContext:
    ...
```
- Extracts bearer credentials from the request.
- Performs constant-time comparison against `settings.raw_admin_api_tokens` and `settings.raw_gateway_api_tokens`.
- Raises `HTTPException(status_code=401, detail="...", headers={"WWW-Authenticate": "Bearer"})` on failure.
- Returns `CallerContext` on success.

### 5.2. `require_admin`
```python
async def require_admin(
    caller: CallerContext = Depends(get_current_token),
) -> CallerContext:
    ...
```
- Asserts that `"admin"` exists in `caller.scopes`.
- Raises `HTTPException(status_code=403, detail="Admin scope required")` if missing.
- Returns `caller` on success.

### 5.3. `require_scope`
```python
def require_scope(required_scope: str) -> Callable[[CallerContext], Coroutine[Any, Any, CallerContext]]:
    ...
```
- Parameterized dependency factory enforcing arbitrary scopes (e.g. `Depends(require_scope("write"))`).
