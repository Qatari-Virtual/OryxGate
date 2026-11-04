# OryxGate API Specification (v1)

## 1. General Principles & Protocols

- **Base URL:** `/api/v1`
- **Protocol:** HTTP/1.1 and HTTP/2 (via ASGI/Uvicorn)
- **Content-Type:** `application/json; charset=utf-8`
- **Authentication:** HTTP Bearer token via `Authorization: Bearer <GATEWAY_API_TOKEN>` header.

### Standard Response Envelope
All successful JSON responses are wrapped in a standard envelope:

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "cached": true,
    "cache_age_seconds": 4.15,
    "timestamp": "2026-11-04T15:30:00Z",
    "request_id": "req_01hxyz123"
  }
}
```

### Standard Error Envelope
Failed responses return appropriate HTTP status codes and a structured error object:

```json
{
  "success": false,
  "error": {
    "code": "AIRCRAFT_NOT_FOUND",
    "message": "Aircraft with registration 'A7-XYZ' was not found in the organization fleet.",
    "detail": null
  },
  "meta": {
    "timestamp": "2026-11-04T15:30:00Z",
    "request_id": "req_01hxyz124"
  }
}
```

---

## 2. Authentication & Authorization

All endpoints except `GET /api/v1/health` require a valid authentication token.

### 2.1. Standard Service-to-Service Header Format
Server-side consumers (Discord bot, WebApp backend, internal automation) authenticate using standard HTTP Bearer tokens:
```http
Authorization: Bearer <GATEWAY_API_TOKEN>
```

### 2.2. Upstream Pilot OAuth Delegation Headers
When performing operations against Infinite Flight v3 that require a specific pilot's permissions (e.g. assigning crew, updating flight plans, booking schedules):
- `X-Pilot-ID: <int>`: The pilot's internal database ID (e.g. `101`).
- `X-IF-User-Id: <uuid>`: The pilot's Infinite Flight user UUID.

OryxGate's `TokenManager` looks up the pilot's stored token in MySQL (`if_live_tokens`), handles automatic token refresh if expired, and delegates that token upstream to IF v3. If omitted on read requests, OryxGate defaults to the organization service account.

### 2.3. Error Codes
- `401 Unauthorized`: Missing or malformed `Authorization` header, or invalid token.
- `403 Forbidden`: Token is valid but lacks the required permission scope (e.g. read-only token attempting `POST /api/v1/pireps`, or non-admin attempting `force_refresh=true`).

---

## 3. Endpoints Reference

### 3.1. System & Cache

#### `GET /api/v1/health`
Checks the service health and upstream connectivity status.
- **Auth Required:** No
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "uptime_seconds": 86420,
    "upstream_status": {
      "if_v3": "connected",
      "if_v2": "connected",
      "crew_center": "connected",
      "database": "connected"
    }
  }
}
```

#### `GET /api/v1/cache/stats`
Returns cache metrics, hit rates, and upstream API call counts.
- **Auth Required:** Yes
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "refetch_count": 142,
    "cache_hits": 9820,
    "hit_ratio": 0.985,
    "last_refetch_time": "2026-11-04T15:28:45Z",
    "cached_aircraft_count": 48,
    "cached_active_flights_count": 6,
    "api_call_counts": {
      "v3_aircraft": 142,
      "v3_schedules": 284,
      "v3_positions": 142,
      "v2_sessions": 24,
      "v2_flights": 720,
      "v2_routes": 45
    }
  }
}
```

#### `POST /api/v1/cache/invalidate`
Forcefully evicts all in-memory cache entries. Future queries will refetch fresh data upstream.
- **Auth Required:** Yes (Requires `admin` scope)
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "message": "Cache invalidated successfully."
  }
}
```

---

### 3.2. Live Fleet & Telemetry

#### `GET /api/v1/fleet/live`
Returns the consolidated live snapshot of the entire organization fleet, including parked ground aircraft, active multiplayer flights, and stopped aircraft.
- **Auth Required:** Yes
- **Query Parameters:**
  - `force_refresh` (boolean, optional, default `false`):
    > [!WARNING]
    > **Admin Only & Debounced:** To prevent triggering upstream Infinite Flight rate-limit bans, `force_refresh=true` is **strictly restricted to tokens with `admin` scope** and is limited by a **mandatory global 15-second debounce window**. Non-admin requests with `force_refresh=true` will ignore this flag and receive cached data; multiple admin requests within 15 seconds will receive cached data with `meta.cached: true`.
  - `status` (string, optional): Filter by state (`STOPPED`, `IN_FLIGHT`, `ON_GROUND`).
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "total_aircraft": 48,
    "active_flights_count": 5,
    "stopped_aircraft_count": 1,
    "parked_aircraft_count": 42,
    "aircraft": [
      {
        "aircraft_id": "c1f1076b-df2b-4ba5-8968-3e4dfcf23d9b",
        "registration": "A7-APA",
        "livery_content_id": "9df4a329-873b-419b-a3ea-ecfa7cf130a0",
        "state": "IN_FLIGHT",
        "is_on_ground": false,
        "is_stopped": false,
        "is_actively_flying": true,
        "telemetry": {
          "latitude": 25.2609,
          "longitude": 51.5651,
          "altitude": 38000,
          "ground_speed": 472.5,
          "heading": 135.0,
          "vertical_speed": 0.0
        },
        "multiplayer": {
          "is_in_multiplayer": true,
          "flight_id": "890d7973-c603-455b-bf92-49eeceb1e227",
          "session_name": "Expert Server",
          "callsign": "QTR101"
        },
        "pilot": {
          "user_id": "2d65f573-0ceb-4139-bf8c-4ae039367468",
          "username": "Ayush"
        },
        "active_schedule": {
          "id": "7df...",
          "callsign": "QTR101",
          "origin_icao": "OTHH",
          "destination_icao": "EGLL"
        }
      }
    ]
  }
}
```

#### `GET /api/v1/fleet/stopped`
Returns only aircraft that are currently stopped in the air (requiring a pilot intervention, e.g. AP+ holding at TOD or paused).
- **Auth Required:** Yes
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "count": 1,
    "stopped_aircraft": [
      {
        "aircraft_id": "b8f047e1-8408-4122-83b3-8cbfa094dbe1",
        "registration": "A7-APC",
        "stopped_since": "2026-11-04T14:15:00Z",
        "stopped_duration_seconds": 4500.0,
        "stopped_display_time": "1.2h ago",
        "stopped_at_tod": true,
        "telemetry": {
          "latitude": 51.1537,
          "longitude": -0.1821,
          "altitude": 12000,
          "ground_speed": 0.0,
          "heading": 260.0
        },
        "last_pilot": {
          "user_id": "9e2c...",
          "username": "PilotAhmed"
        },
        "active_schedule": {
          "callsign": "QTR003",
          "origin_icao": "OTHH",
          "destination_icao": "EGLL"
        }
      }
    ]
  }
}
```

#### `GET /api/v1/fleet/aircraft/{registration_or_id}`
Returns telemetry, persistence state, and schedule status for a single aircraft.
- **Auth Required:** Yes
- **Path Parameters:**
  - `registration_or_id`: Registration (e.g. `A7-APC` or `A7APC`) or aircraft UUID.

---

### 3.3. Flights & Routes

#### `GET /api/v1/flights/{flight_id}/route`
Fetches the route breadcrumb trail for an active or recent flight.
- **Auth Required:** Yes
- **Caching:** 60 seconds TTL

#### `GET /api/v1/flights/{flight_id}/flightplan`
Fetches the active filed flight plan (waypoints) for a flight.
- **Auth Required:** Yes

---

### 3.4. PIREPs & Crew Center

#### `POST /api/v1/pireps`
Submits an approved or pilot-filed PIREP to the Crew Center PHP API.
- **Auth Required:** Yes (Requires `write` scope)
- **Request Body:**
```json
{
  "pilot_id": 2,
  "flight_num": "1234",
  "departure": "EGLL",
  "arrival": "OTHH",
  "flight_time": "06:45",
  "date": "2026-11-04",
  "aircraft_id": 6,
  "fuel_used": 28500.0,
  "multiplier": "Event"
}
```
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": 0,
    "pirep_id": 14920,
    "message": "PIREP submitted successfully."
  }
}
```

#### `GET /api/v1/aircraft/catalog`
Returns mapping of aircraft names and ICAO types to Crew Center database IDs.
- **Auth Required:** Yes
- **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "A359": 14,
    "A35K": 18,
    "B77W": 2,
    "B789": 7
  }
}
```
