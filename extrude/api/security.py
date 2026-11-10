"""Bounds and browser protections for the single-process server.

Hosted data routes require an explicitly configured interim shared bearer token.
This is not tenant isolation; local mode is for a trusted loopback operator only.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import secrets
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, RedirectResponse

_LOG = logging.getLogger("extrude.security")
MAX_BODY = 1024 * 1024
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def hosted() -> bool:
    return os.environ.get("RENDER") == "true" or os.environ.get("EXTRUDE_HOSTED") == "1"


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.reads = deque()
        self.writes = deque()
        self.denials = deque()
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        path = scope["path"]
        protected = path.startswith(("/v1/", "/artifacts/"))
        category = "api" if path.startswith("/v1/") else "artifact" if protected else "page"
        secure = scope.get("scheme") == "https"

        async def secured_send(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                         (b"referrer-policy", b"no-referrer"), (b"content-security-policy", CSP.encode())]
                if secure:
                    extra.append((b"strict-transport-security", b"max-age=31536000"))
                if protected:
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = [*message.get("headers", []), *extra]
                if message["status"] >= 400:
                    event = {"time": datetime.now(timezone.utc).isoformat(), "event": "request_rejected",
                             "route": getattr(scope.get("route"), "path", category), "method": scope["method"], "status": message["status"],
                             "ip": (scope.get("client") or (None,))[0],
                             "agent_hash": hashlib.sha256(headers.get(b"user-agent", b"")).hexdigest()[:16]}
                    _LOG.warning(json.dumps(event))
            await send(message)

        async def reject(status, detail, retry=False):
            response = JSONResponse({"detail": detail}, status_code=status,
                                    headers={"Retry-After": "60"} if retry else None)
            return await response(scope, receive, secured_send)

        if hosted() and not secure:
            # Uvicorn must trust forwarded proto only from the deployment proxy.
            origin = os.environ.get("EXTRUDE_PUBLIC_ORIGIN", "").rstrip("/")
            parsed = urlsplit(origin)
            if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                return await reject(503, "HTTPS deployment configuration required.")
            # Fixed destination, never an attacker-controlled Host header.
            return await RedirectResponse(origin + path, status_code=308)(scope, receive, secured_send)
        if not hosted():
            host = headers.get(b"host", b"").decode("latin1").lower()
            host = host.split("]", 1)[0] + "]" if host.startswith("[") else host.split(":", 1)[0]
            if host not in {"127.0.0.1", "localhost", "testserver", "[::1]"}:
                return await reject(403, "Trusted local host required.")
        token = os.environ.get("EXTRUDE_API_TOKEN", "")
        if protected and (hosted() or token):
            scheme, _, supplied = headers.get(b"authorization", b"").partition(b" ")
            configured = len(token.encode()) >= 32
            if not configured or scheme.lower() != b"bearer" or not secrets.compare_digest(supplied, token.encode()):
                # Anonymous traffic must not spend the authenticated compute budget.
                now = time.monotonic()
                while self.denials and self.denials[0] <= now - 60:
                    self.denials.popleft()
                if len(self.denials) >= 10:
                    return await reject(429, "Access attempt budget exceeded. Retry later.", retry=True)
                self.denials.append(now)
                return await reject(401 if configured else 503, "Shared access token required." if configured
                                    else "Shared access is not configured. Contact the operator.")
        if protected:
            now = time.monotonic()
            queue = self.reads if scope["method"] in {"GET", "HEAD", "OPTIONS"} else self.writes
            while queue and queue[0] <= now - 60:
                queue.popleft()
            limited = hosted() or os.environ.get("EXTRUDE_RATE_LIMIT") == "1"
            if limited and (len(queue) >= (120 if queue is self.reads else 10) or self.active >= 2):
                return await reject(429, "Server request budget exceeded. Retry later.", retry=True)
            if limited:
                queue.append(now)
        if protected and hosted() and (path.startswith("/v1/projects") or
                                      path in {"/v1/design", "/v1/compare", "/v1/copilot"}):
            return await reject(403, "This trusted-local feature is disabled on hosted deployments.")
        if protected:
            origin = headers.get(b"origin")
            if origin:
                expected = os.environ.get("EXTRUDE_PUBLIC_ORIGIN", "").rstrip("/")
                if not expected:
                    expected = f"{scope.get('scheme', 'http')}://" + headers.get(b"host", b"").decode("latin1")
                if origin.decode("latin1") != expected:
                    return await reject(403, "Origin not permitted.")
            if headers.get(b"sec-fetch-site") == b"cross-site":
                return await reject(403, "Cross-site API requests are not permitted.")
        if protected:
            self.active += 1
        started = False

        async def track_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await secured_send(message)

        try:
            # Bound declared AND actual bytes before JSON parsing or running any tool.
            try:
                declared = int(headers.get(b"content-length", b"0"))
            except ValueError:
                return await reject(400, "Invalid Content-Length.")
            if declared < 0:
                return await reject(400, "Invalid Content-Length.")
            if declared > MAX_BODY:
                return await reject(413, "Request exceeds 1 MiB limit.")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY:
                    return await reject(413, "Request exceeds 1 MiB limit.")
                if not message.get("more_body", False):
                    break
            if body and protected and headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
                return await reject(415, "Only application/json request bodies are accepted.")

            delivered = False

            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, track_send)
        except Exception:
            # No exception text, request body, query, token or filesystem paths in logs.
            if not started:
                await reject(500, "Internal server error.")
        finally:
            if protected:
                self.active -= 1
