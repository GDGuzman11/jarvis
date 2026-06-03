---
name: lifespan-testing
description: How to test FastAPI ASGI lifespan side effects (init_db, agent startup) — ASGITransport does NOT run lifespan
metadata:
  type: reference
---

To test FastAPI lifespan side effects (e.g. `init_db` running on startup, agents spawning), you must drive the lifespan explicitly. `httpx.ASGITransport` only drives the HTTP scope — it does NOT run the ASGI lifespan, so startup hooks never fire and `/health` still answers.

**Why:** Discovered while verifying Phase 2 "FastAPI app with lifespan context manager". A test using `httpx.AsyncClient(transport=ASGITransport(app))` passed `/health` but the DB was never created because `init_db` (in the lifespan) never ran.

**How to apply:**
- For HTTP response contract only -> `httpx.AsyncClient` + `ASGITransport` is fine.
- To assert lifespan side effects -> use Starlette `TestClient` as a context manager (`with TestClient(app): ...`), which runs startup on `__enter__` and shutdown on `__exit__`. `asgi_lifespan` is NOT installed in the venv.
- `TestClient` spins its own event loop, so from within an already-running async loop call it via `asyncio.to_thread`.
- The lifespan's `init_db()` writes to `backend.memory.database.DEFAULT_DB_PATH` (= `C:\Users\User\appsbyG\Jarvis\data\jarvis.db`). It calls `init_db()` with no args, so reassigning the module attribute after import does NOT redirect it (the default is bound at function definition). To observe a fresh init, delete the DB file first then check tables reappear.
- When grepping `backend/main.py` for `0.0.0.0` (Security Rule 2), exclude comment lines and "never 0.0.0.0" warnings — the file legitimately contains warning comments. Assert on the `HOST` constant value instead.
- To trigger a server-side broadcast (`backend.websocket_hub.hub.broadcast`) while WS clients are connected via `client.websocket_connect("/ws")`, call it on the server's event loop with `client.portal.call(hub.broadcast, event)` — the hub and connections live on that loop, so calling `hub.broadcast` directly from the test thread would not match. Then `ws.receive_json()` on each client. The hub gates sends on `ws.application_state == WebSocketState.CONNECTED`.

venv python (uv not on PATH): `C:\Users\User\appsbyG\Jarvis\.venv\Scripts\python.exe`. See [[uv-path]].
