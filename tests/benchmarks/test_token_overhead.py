"""Token overhead benchmark for Synd's MCP tools.

Measures the token cost of:
  1. Tool schema injection — what every MCP session pays upfront
  2. search responses (summaries only) and fetch responses (full content)
  3. The two-step progressive disclosure pattern vs. naive full fetch

Token counting uses len(str) // 4 throughout, consistent with the project
convention in synd/storage/models.py. This is an approximation (~±15%
for English prose). For exact cl100k counts install tiktoken and replace
_count_tokens below.

Run:
    pytest tests/benchmarks/ --benchmark -v -s

Results are written to tests/benchmarks/results/latest.json.
Before tagging a release, copy that file to results/{version}.json and
commit it alongside the tag. See RELEASES.md for the full procedure.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import synd
from synd.server import create_server
from synd.server import fetch_docs as _fetch_docs
from synd.server import search_docs as _search_docs
from synd.storage.db import Database
from synd.storage.models import Chunk, Pack, Page

RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# Token counter — swap in tiktoken here for exact cl100k counts
# ---------------------------------------------------------------------------


def _count_tokens(text: str) -> int:
    return len(text) // 4


# ---------------------------------------------------------------------------
# Realistic benchmark corpus — 20 chunks across 4 documentation themes
# ---------------------------------------------------------------------------

_PACK = Pack(
    name="mylib",
    version="2.0.0",
    lifecycle_state="approved",
    doc_version_status="stable",
    indexed_at="2026-05-20T00:00:00Z",
    policy_profile="default",
    pack_digest="sha256:benchmark",
    normalized_content_hash="sha256:benchmark",
    source_url="docs/",
    source_commit="benchmark",
    owner="benchmark",
)

_PAGES = [
    Page(
        id=1,
        package="mylib",
        version="2.0.0",
        url="docs/auth.md",
        title="Authentication",
    ),
    Page(
        id=2,
        package="mylib",
        version="2.0.0",
        url="docs/config.md",
        title="Configuration",
    ),
    Page(
        id=3, package="mylib", version="2.0.0", url="docs/api.md", title="API Reference"
    ),
    Page(
        id=4,
        package="mylib",
        version="2.0.0",
        url="docs/integration.md",
        title="Integration",
    ),
]

_CHUNKS_DATA = [
    # --- Authentication (page_id=1) ---
    (
        1,
        "docs/auth / OAuth2 / Getting started",
        "Configure OAuth2 authorization code flow with PKCE for browser-based clients.",
        (
            "OAuth2 authorization code flow with PKCE is the recommended pattern for "
            "browser-based and mobile clients. To configure it, register your application "
            "in the developer console and note the client_id. Set redirect_uri to a route "
            "your application controls.\n\n"
            "Initialize the OAuth2 client:\n\n"
            "    from mylib.auth import OAuth2Client\n"
            "    client = OAuth2Client(\n"
            "        client_id='your-client-id',\n"
            "        redirect_uri='https://your-app.example.com/callback',\n"
            "        scopes=['read:profile', 'write:data'],\n"
            "    )\n\n"
            "Call client.authorize_url() to build the authorization URL, including a "
            "cryptographically random state parameter and a PKCE code_challenge. Redirect "
            "the user to this URL. After the user authenticates, the provider redirects "
            "to your redirect_uri with a code parameter. Exchange the code for tokens:\n\n"
            "    tokens = await client.exchange_code(code=request.params['code'],\n"
            "                                        state=request.params['state'])\n\n"
            "The returned TokenSet includes access_token, refresh_token, and expires_at. "
            "Store the refresh_token securely — it is used to obtain new access tokens "
            "after expiry without re-prompting the user."
        ),
    ),
    (
        1,
        "docs/auth / OAuth2 / Token refresh",
        "Refresh an expired access token using the stored refresh token.",
        (
            "Access tokens issued by mylib expire after one hour by default. When a "
            "request returns HTTP 401 Unauthorized, refresh the access token automatically:\n\n"
            "    from mylib.auth import TokenExpiredError\n\n"
            "    try:\n"
            "        result = await api.get('/resource')\n"
            "    except TokenExpiredError:\n"
            "        tokens = await client.refresh(refresh_token=stored_refresh_token)\n"
            "        result = await api.get('/resource')\n\n"
            "The SDK includes a middleware class that handles this automatically if you "
            "prefer not to manage the retry logic yourself:\n\n"
            "    from mylib.middleware import AutoRefreshMiddleware\n"
            "    api = MyLibClient(middleware=[AutoRefreshMiddleware(client)])\n\n"
            "Refresh tokens are single-use. Each successful refresh issues a new "
            "refresh_token — always persist the latest value. Refresh tokens expire after "
            "30 days of inactivity or when the user revokes access."
        ),
    ),
    (
        1,
        "docs/auth / API keys / Generating keys",
        "Generate and rotate API keys for server-to-server authentication.",
        (
            "API keys are suitable for server-to-server integrations where a human login "
            "flow is not appropriate. Generate a key in the dashboard under Settings → "
            "API Keys → New Key. Keys are shown only once at creation; store them in your "
            "secrets manager immediately.\n\n"
            "Authenticate requests by setting the Authorization header:\n\n"
            "    headers = {'Authorization': f'Bearer {api_key}'}\n\n"
            "Or use the SDK constructor:\n\n"
            "    from mylib import Client\n"
            "    client = Client(api_key='mlk_live_...')\n\n"
            "Keys have an optional expiry date and can be scoped to specific permissions. "
            "The recommended rotation policy is 90 days for production keys. Use the "
            "client.keys.rotate() method to generate a replacement before the old key "
            "expires, ensuring zero downtime during rotation."
        ),
    ),
    (
        1,
        "docs/auth / JWT / Verifying tokens",
        "Verify incoming JWT tokens issued by mylib using the public key endpoint.",
        (
            "If your application receives JWTs from mylib (for example, in a webhook "
            "payload or a server-side session), verify the signature before trusting any "
            "claims. mylib publishes its public keys at the JWKS URI:\n\n"
            "    https://api.mylib.example.com/.well-known/jwks.json\n\n"
            "Use the PyJWT library with the JWKS client:\n\n"
            "    from jwt import PyJWKClient\n"
            "    jwks_client = PyJWKClient('https://api.mylib.example.com/.well-known/jwks.json')\n"
            "    signing_key = jwks_client.get_signing_key_from_jwt(token)\n"
            "    payload = jwt.decode(token, signing_key.key, algorithms=['RS256'],\n"
            "                        audience='your-client-id')\n\n"
            "Always validate the aud (audience) claim to prevent token reuse across "
            "applications. The iss (issuer) claim must match "
            "https://api.mylib.example.com. Reject tokens with exp in the past."
        ),
    ),
    (
        1,
        "docs/auth / SSO / SAML configuration",
        "Configure SAML 2.0 single sign-on for enterprise identity providers.",
        (
            "mylib supports SAML 2.0 SP-initiated SSO for enterprise customers using "
            "Okta, Azure AD, Google Workspace, or any standards-compliant IdP. "
            "Before configuring, collect the following from your IdP administrator:\n\n"
            "- Entity ID (Issuer)\n"
            "- SSO URL (Single Sign-On endpoint)\n"
            "- X.509 certificate (for signature verification)\n\n"
            "In the mylib dashboard, navigate to Organization → Security → SAML. "
            "Enter the IdP details and download the SP metadata XML to upload to your IdP. "
            "The SP entity ID is https://api.mylib.example.com/saml/metadata.\n\n"
            "SAML assertions must include the email attribute mapped to "
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress. "
            "Additional attribute mappings (first name, last name, groups) are optional "
            "but recommended for provisioning. Enable JIT (Just-In-Time) provisioning "
            "to automatically create user accounts on first login."
        ),
    ),
    # --- Configuration (page_id=2) ---
    (
        2,
        "docs/config / Database / Connection pool",
        "Configure database connection pooling for high-throughput applications.",
        (
            "mylib uses SQLAlchemy under the hood and exposes connection pool settings "
            "through the database configuration block. For most production workloads, "
            "start with these defaults:\n\n"
            "    DATABASE = {\n"
            "        'url': 'postgresql+asyncpg://user:pass@host/dbname',\n"
            "        'pool_size': 10,\n"
            "        'max_overflow': 20,\n"
            "        'pool_timeout': 30,\n"
            "        'pool_recycle': 1800,\n"
            "    }\n\n"
            "pool_size is the number of connections maintained in the pool at all times. "
            "max_overflow allows temporary bursts above pool_size. pool_recycle closes "
            "and replaces connections older than 1800 seconds to prevent stale connections "
            "after network interruptions or database restarts.\n\n"
            "For read-heavy workloads, add a read replica:\n\n"
            "    DATABASE['read_url'] = 'postgresql+asyncpg://user:pass@replica/dbname'\n\n"
            "mylib will route SELECT queries to the replica automatically when read_url "
            "is set. Write operations always go to the primary."
        ),
    ),
    (
        2,
        "docs/config / Cache / Redis setup",
        "Configure Redis as the cache backend for session storage and rate limiting.",
        (
            "Redis is required for session storage, rate limiting, and distributed locking "
            "in multi-process deployments. Configure the Redis connection:\n\n"
            "    CACHE = {\n"
            "        'backend': 'redis',\n"
            "        'url': 'redis://localhost:6379/0',\n"
            "        'max_connections': 50,\n"
            "        'socket_timeout': 5,\n"
            "        'key_prefix': 'mylib:',\n"
            "    }\n\n"
            "In production, use Redis Sentinel or Redis Cluster for high availability. "
            "For Sentinel:\n\n"
            "    CACHE = {\n"
            "        'backend': 'redis-sentinel',\n"
            "        'sentinels': [('sentinel1', 26379), ('sentinel2', 26379)],\n"
            "        'master': 'mymaster',\n"
            "    }\n\n"
            "Set a key_prefix to namespace cache keys if multiple applications share "
            "a Redis instance. The default TTL for session keys is 3600 seconds; "
            "override per-key with the ttl parameter on cache.set()."
        ),
    ),
    (
        2,
        "docs/config / Logging / Structured output",
        "Enable structured JSON logging for production log aggregation pipelines.",
        (
            "mylib emits Python standard library logging calls throughout. To emit "
            "structured JSON instead of plaintext, configure the JsonFormatter:\n\n"
            "    import logging\n"
            "    from mylib.logging import JsonFormatter\n\n"
            "    handler = logging.StreamHandler()\n"
            "    handler.setFormatter(JsonFormatter())\n"
            "    logging.getLogger('mylib').addHandler(handler)\n"
            "    logging.getLogger('mylib').setLevel(logging.INFO)\n\n"
            "Each log record includes timestamp (ISO 8601), level, logger, message, "
            "and any extra fields passed to the log call. Request-scoped fields like "
            "request_id and user_id are automatically included when the AsyncContextMiddleware "
            "is active.\n\n"
            "To forward logs to Datadog, Splunk, or an ELK stack, pipe stdout to your "
            "log shipper. No additional SDK configuration is required — structured JSON "
            "on stdout is the recommended integration pattern."
        ),
    ),
    (
        2,
        "docs/config / Environment / Variables reference",
        "Complete reference of environment variables that override configuration file settings.",
        (
            "All configuration values can be overridden with environment variables, "
            "which take precedence over the configuration file. Variables follow the "
            "pattern MYLIB_{SECTION}_{KEY} in uppercase:\n\n"
            "    MYLIB_DATABASE_URL          Database connection URL\n"
            "    MYLIB_DATABASE_POOL_SIZE    Connection pool size (default: 10)\n"
            "    MYLIB_CACHE_URL             Redis connection URL\n"
            "    MYLIB_CACHE_KEY_PREFIX      Cache key namespace (default: 'mylib:')\n"
            "    MYLIB_AUTH_SECRET_KEY       HMAC signing key for session tokens\n"
            "    MYLIB_AUTH_TOKEN_TTL        Access token lifetime in seconds (default: 3600)\n"
            "    MYLIB_LOG_LEVEL             Logging level (default: INFO)\n"
            "    MYLIB_LOG_FORMAT            'json' or 'text' (default: 'json')\n\n"
            "Boolean values accept '1', 'true', 'yes' (case-insensitive) as truthy. "
            "List values are comma-separated: MYLIB_ALLOWED_HOSTS=example.com,api.example.com. "
            "Environment variables are validated at startup; invalid values raise "
            "ConfigurationError with the offending variable name."
        ),
    ),
    (
        2,
        "docs/config / Settings / Validation",
        "Validate configuration at startup to catch misconfigurations before handling requests.",
        (
            "mylib validates the full configuration object at startup using Pydantic. "
            "If any required value is missing or a value fails a constraint, "
            "ConfigurationError is raised before the server accepts connections. "
            "This ensures misconfigured deployments fail fast rather than producing "
            "intermittent runtime errors.\n\n"
            "To validate your configuration in CI without starting the server:\n\n"
            "    python -m mylib validate-config\n\n"
            "Exit code 0 means the configuration is valid. Non-zero exit codes print "
            "a structured error listing all invalid fields.\n\n"
            "Custom validators can be added for application-specific rules:\n\n"
            "    from mylib.config import register_validator\n\n"
            "    @register_validator\n"
            "    def check_allowed_hosts(config):\n"
            "        if config.DEBUG and '*' not in config.ALLOWED_HOSTS:\n"
            "            raise ValueError('DEBUG mode requires ALLOWED_HOSTS = [\"*\"]')\n\n"
            "Validators run in registration order and all errors are collected before "
            "raising, so a single validation pass reports all problems at once."
        ),
    ),
    # --- API Reference (page_id=3) ---
    (
        3,
        "docs/api / Endpoints / Pagination",
        "Use cursor-based pagination to iterate through large result sets efficiently.",
        (
            "All list endpoints in the mylib API use cursor-based pagination. "
            "Responses include a next_cursor field when more results are available:\n\n"
            "    GET /v2/items?limit=50\n\n"
            "    {\n"
            "      'items': [...],\n"
            "      'next_cursor': 'eyJpZCI6MTAwfQ',\n"
            "      'has_more': true\n"
            "    }\n\n"
            "Pass next_cursor as the cursor query parameter to fetch the next page:\n\n"
            "    GET /v2/items?limit=50&cursor=eyJpZCI6MTAwfQ\n\n"
            "Cursors are opaque — do not decode or construct them manually. They expire "
            "after 10 minutes of inactivity, so complete pagination in a single session. "
            "The SDK provides an async iterator that handles pagination transparently:\n\n"
            "    async for item in client.items.list(limit=50):\n"
            "        process(item)\n\n"
            "The default limit is 20; the maximum is 100. Setting limit=0 is invalid "
            "and returns HTTP 400."
        ),
    ),
    (
        3,
        "docs/api / Rate limits / Headers",
        "Read X-RateLimit headers to monitor remaining quota and implement backoff.",
        (
            "Every API response includes rate limit headers:\n\n"
            "    X-RateLimit-Limit: 1000\n"
            "    X-RateLimit-Remaining: 874\n"
            "    X-RateLimit-Reset: 1716220800\n\n"
            "Limit is the quota for the current window (1000 requests per 15 minutes "
            "for standard plans). Remaining decreases with each request. Reset is a Unix "
            "timestamp for when the quota refills.\n\n"
            "When Remaining reaches 0, requests return HTTP 429 Too Many Requests with "
            "a Retry-After header indicating the seconds to wait:\n\n"
            "    HTTP/1.1 429 Too Many Requests\n"
            "    Retry-After: 47\n\n"
            "Implement exponential backoff with jitter:\n\n"
            "    import random, asyncio\n"
            "    async def with_backoff(fn, max_retries=3):\n"
            "        for attempt in range(max_retries):\n"
            "            try:\n"
            "                return await fn()\n"
            "            except RateLimitError as e:\n"
            "                if attempt == max_retries - 1: raise\n"
            "                await asyncio.sleep(e.retry_after + random.uniform(0, 1))\n\n"
            "The SDK retries 429 responses automatically with exponential backoff. "
            "Set max_retries=0 to disable automatic retries."
        ),
    ),
    (
        3,
        "docs/api / Webhooks / Signature verification",
        "Verify webhook signatures to confirm payloads originate from mylib.",
        (
            "mylib signs webhook payloads with HMAC-SHA256 using your webhook secret. "
            "Always verify the signature before processing a webhook:\n\n"
            "    import hmac, hashlib\n"
            "    from mylib.webhooks import WebhookVerificationError\n\n"
            "    def verify_webhook(payload: bytes, signature: str, secret: str) -> None:\n"
            "        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()\n"
            "        received = signature.removeprefix('sha256=')\n"
            "        if not hmac.compare_digest(expected, received):\n"
            "            raise WebhookVerificationError('Invalid signature')\n\n"
            "The signature is in the X-Mylib-Signature header. Use hmac.compare_digest "
            "to prevent timing attacks. Reject payloads older than 5 minutes using the "
            "X-Mylib-Timestamp header:\n\n"
            "    import time\n"
            "    ts = int(request.headers['X-Mylib-Timestamp'])\n"
            "    if abs(time.time() - ts) > 300:\n"
            "        raise WebhookVerificationError('Payload too old')\n\n"
            "Register webhook endpoints in the dashboard under Settings → Webhooks. "
            "Each endpoint can subscribe to specific event types."
        ),
    ),
    (
        3,
        "docs/api / Errors / Status codes",
        "Reference of HTTP status codes returned by the mylib API and their meanings.",
        (
            "The mylib API returns standard HTTP status codes with a consistent JSON "
            "error body:\n\n"
            "    {\n"
            "      'error': {\n"
            "        'code': 'validation_error',\n"
            "        'message': 'The field email is required.',\n"
            "        'field': 'email',\n"
            "        'request_id': 'req_01J8...'\n"
            "      }\n"
            "    }\n\n"
            "Common status codes:\n\n"
            "    400 Bad Request        — Invalid parameters; see error.field\n"
            "    401 Unauthorized       — Missing or invalid authentication\n"
            "    403 Forbidden          — Authenticated but lacks permission\n"
            "    404 Not Found          — Resource does not exist\n"
            "    409 Conflict           — State conflict (e.g., duplicate key)\n"
            "    422 Unprocessable      — Request parsed but semantically invalid\n"
            "    429 Too Many Requests  — Rate limit exceeded; see Retry-After\n"
            "    500 Internal Error     — Server error; retry is appropriate\n"
            "    503 Service Unavailable — Temporary outage; retry with backoff\n\n"
            "Always include request_id when contacting support. 5xx errors are "
            "idempotent-safe to retry with exponential backoff."
        ),
    ),
    (
        3,
        "docs/api / Endpoints / Filtering and sorting",
        "Apply field filters and sort orders to list endpoint queries.",
        (
            "List endpoints accept filter and sort query parameters:\n\n"
            "    GET /v2/items?filter[status]=active&filter[created_after]=2026-01-01\n"
            "    GET /v2/items?sort=-created_at,name\n\n"
            "Filters use bracket notation: filter[field]=value. Multiple filters are "
            "ANDed together. Supported operators can be appended to field names:\n\n"
            "    filter[amount_gte]=100    (greater than or equal)\n"
            "    filter[name_contains]=api  (case-insensitive substring)\n"
            "    filter[tags_any]=billing,admin  (comma-separated, OR logic)\n\n"
            "Sorting accepts a comma-separated list of field names. Prefix with - "
            "for descending order. Multiple sort fields are applied left to right.\n\n"
            "Available filter fields and sort keys are listed per-endpoint in the "
            "API reference. Filtering on non-indexed fields returns HTTP 400 with "
            "error code unsupported_filter. The SDK translates Python keyword arguments "
            "to filter syntax automatically:\n\n"
            "    items = await client.items.list(status='active', sort='-created_at')"
        ),
    ),
    # --- Integration (page_id=4) ---
    (
        4,
        "docs/integration / Django / Middleware setup",
        "Install mylib middleware in a Django project for request context and auth.",
        (
            "Add mylib's Django middleware to MIDDLEWARE in settings.py. Order matters — "
            "place mylib middleware after SessionMiddleware but before any application "
            "middleware that needs access to the authenticated user:\n\n"
            "    MIDDLEWARE = [\n"
            "        'django.middleware.security.SecurityMiddleware',\n"
            "        'django.contrib.sessions.middleware.SessionMiddleware',\n"
            "        'mylib.django.AuthMiddleware',        # must come after session\n"
            "        'mylib.django.RequestContextMiddleware',\n"
            "        'django.middleware.common.CommonMiddleware',\n"
            "        ...\n"
            "    ]\n\n"
            "AuthMiddleware attaches the authenticated user and token set to request.mylib_user "
            "and request.mylib_tokens. It validates the session token on every request and "
            "handles token refresh transparently.\n\n"
            "RequestContextMiddleware propagates the request_id and user_id to all log "
            "records emitted during the request, enabling correlation across log lines.\n\n"
            "Configure the mylib app settings in settings.py:\n\n"
            "    MYLIB = {\n"
            "        'API_KEY': env('MYLIB_API_KEY'),\n"
            "        'ENVIRONMENT': 'production',\n"
            "    }"
        ),
    ),
    (
        4,
        "docs/integration / FastAPI / Dependency injection",
        "Use mylib authentication as a FastAPI dependency for route protection.",
        (
            "mylib provides a FastAPI-compatible dependency that validates the Bearer token "
            "on each request and returns the authenticated user:\n\n"
            "    from fastapi import FastAPI, Depends\n"
            "    from mylib.fastapi import require_auth, AuthenticatedUser\n\n"
            "    app = FastAPI()\n\n"
            "    @app.get('/profile')\n"
            "    async def get_profile(user: AuthenticatedUser = Depends(require_auth)):\n"
            "        return {'id': user.id, 'email': user.email}\n\n"
            "require_auth raises HTTP 401 if the token is missing or invalid, and HTTP 403 "
            "if the token lacks the required scopes. To require specific scopes:\n\n"
            "    from mylib.fastapi import require_scope\n\n"
            "    @app.post('/admin/action')\n"
            "    async def admin_action(\n"
            "        user: AuthenticatedUser = Depends(require_scope('admin:write'))\n"
            "    ):\n"
            "        ...\n\n"
            "The lifespan parameter on FastAPI should initialise and close the mylib client:\n\n"
            "    from contextlib import asynccontextmanager\n"
            "    from mylib import Client\n\n"
            "    @asynccontextmanager\n"
            "    async def lifespan(app):\n"
            "        app.state.mylib = Client(api_key=settings.MYLIB_API_KEY)\n"
            "        yield\n"
            "        await app.state.mylib.close()"
        ),
    ),
    (
        4,
        "docs/integration / Async / Concurrency patterns",
        "Run mylib API calls concurrently using asyncio.gather for parallel requests.",
        (
            "The mylib async client is safe to use concurrently. Use asyncio.gather "
            "to issue multiple API calls in parallel:\n\n"
            "    import asyncio\n"
            "    from mylib import AsyncClient\n\n"
            "    async def fetch_user_data(user_id: str):\n"
            "        async with AsyncClient(api_key=API_KEY) as client:\n"
            "            profile, orders, invoices = await asyncio.gather(\n"
            "                client.users.get(user_id),\n"
            "                client.orders.list(user_id=user_id),\n"
            "                client.invoices.list(user_id=user_id),\n"
            "            )\n"
            "        return profile, orders, invoices\n\n"
            "Each coroutine uses a connection from the shared pool. The pool size limits "
            "true parallelism — gathering 50 coroutines with pool_size=10 processes them "
            "in batches of 10. Increase pool_size in DATABASE config if you need higher "
            "sustained concurrency.\n\n"
            "Avoid creating a new AsyncClient per request — reuse a single client instance "
            "across the application lifetime to share the connection pool and avoid "
            "connection overhead on every request."
        ),
    ),
    (
        4,
        "docs/integration / Testing / Mock client",
        "Use MyLibMock to write unit tests without making real API calls.",
        (
            "mylib ships a mock client for testing that records calls and returns "
            "configurable responses without hitting the network:\n\n"
            "    from mylib.testing import MyLibMock\n\n"
            "    def test_creates_order():\n"
            "        mock = MyLibMock()\n"
            "        mock.orders.create.returns({'id': 'ord_123', 'status': 'pending'})\n\n"
            "        result = my_service.create_order(client=mock, amount=100)\n\n"
            "        assert result.order_id == 'ord_123'\n"
            "        mock.orders.create.assert_called_once_with(amount=100)\n\n"
            "MyLibMock implements the full Client interface, so it can be injected "
            "anywhere a real Client is expected. Configure error responses to test "
            "failure paths:\n\n"
            "    from mylib import RateLimitError\n"
            "    mock.orders.create.raises(RateLimitError(retry_after=2))\n\n"
            "For integration tests that need realistic response shapes, use "
            "MyLibMock.from_fixture(path) to load JSON response fixtures. "
            "Fixtures are validated against the current response schema on load, "
            "so outdated fixtures fail loudly."
        ),
    ),
    (
        4,
        "docs/integration / Async / Error handling",
        "Handle network errors and retries in async contexts with structured exception types.",
        (
            "mylib raises structured exceptions for all error conditions. The exception "
            "hierarchy is:\n\n"
            "    MylibError\n"
            "    ├── APIError              — HTTP 4xx/5xx from the API\n"
            "    │   ├── AuthenticationError  (401)\n"
            "    │   ├── PermissionError      (403)\n"
            "    │   ├── NotFoundError        (404)\n"
            "    │   ├── ConflictError        (409)\n"
            "    │   ├── RateLimitError       (429, has retry_after attribute)\n"
            "    │   └── ServerError          (5xx)\n"
            "    ├── NetworkError         — connection failure, timeout\n"
            "    └── ConfigurationError   — invalid SDK configuration\n\n"
            "Catch at the appropriate level of specificity:\n\n"
            "    from mylib import RateLimitError, NetworkError, APIError\n\n"
            "    try:\n"
            "        result = await client.items.create(**data)\n"
            "    except RateLimitError as e:\n"
            "        await asyncio.sleep(e.retry_after)\n"
            "        result = await client.items.create(**data)\n"
            "    except NetworkError:\n"
            "        # Retry with backoff — request may not have reached the server\n"
            "        ...\n"
            "    except APIError as e:\n"
            "        logger.error('API error', extra={'request_id': e.request_id})\n"
            "        raise\n\n"
            "ServerError (5xx) is safe to retry; AuthenticationError and PermissionError "
            "are not — retrying will not change the outcome."
        ),
    ),
]


def _build_chunks() -> list[Chunk]:
    chunks = []
    for i, (page_id, heading, summary, content) in enumerate(_CHUNKS_DATA, start=1):
        chunks.append(
            Chunk(
                id=i,
                package="mylib",
                version="2.0.0",
                page_id=page_id,
                heading_path=heading,
                summary=summary,
                content=content,
                token_count=len(content) // 4,
                source_url=f"docs/page{page_id}.md",
                source_commit="benchmark",
                content_hash=f"sha256:chunk{i:02d}",
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bench_db(tmp_path_factory: pytest.TempPathFactory) -> Database:
    path = tmp_path_factory.mktemp("bench") / ".synd" / "index.db"
    db = Database(path)
    db.create_schema()
    # page_id FK note: first import into a fresh DB — AUTOINCREMENT assigns
    # ids 1..4 matching _PAGES order, so chunk page_id references align.
    # See todo.md: db.py:121-126 bug affects second-and-later imports only.
    db.import_pack(_PACK, _PAGES, _build_chunks())
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response_tokens(result: dict[str, Any]) -> int:
    return _count_tokens(json.dumps(result))


def _schema_measurements() -> dict[str, Any]:
    server = create_server()
    tools = server._tool_manager.list_tools()
    per_tool = []
    total = 0
    for t in tools:
        raw = json.dumps(
            {"name": t.name, "description": t.description, "inputSchema": t.parameters}
        )
        tokens = _count_tokens(raw)
        total += tokens
        per_tool.append({"name": t.name, "tokens": tokens, "chars": len(raw)})
    return {
        "total_tokens": total,
        "tools": per_tool,
        "pct_of_200k_context": round(total / 200_000 * 100, 3),
        "pct_of_128k_context": round(total / 128_000 * 100, 3),
    }


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_token_overhead(bench_db: Database) -> None:
    corpus_chunks = _build_chunks()
    corpus_summary_chars = sum(len(c.summary or "") for c in corpus_chunks)
    corpus_content_chars = sum(len(c.content or "") for c in corpus_chunks)

    schema = _schema_measurements()

    # Broad OR query — FTS5 implicit AND would require all terms in one chunk;
    # OR syntax ensures we get results across all four documentation themes.
    broad_query = (
        "oauth2 OR refresh OR jwt OR saml OR "
        "database OR redis OR logging OR validate OR "
        "pagination OR webhook OR filters OR "
        "django OR fastapi OR asyncio OR mock OR network"
    )

    # Responses at different result counts via the public API.
    # summary_nN: cost of search_docs at limit=N.
    # full_nN: cost of fetch_docs for the top N chunk IDs (two-step, agentless).
    response_data: dict[str, dict[str, Any]] = {}
    for n in (5, 10, 20):
        s_result = _search_docs(bench_db, broad_query, limit=n)
        s_results = s_result.get("results", [])
        s_tokens = _response_tokens(s_result)
        response_data[f"summary_n{n}"] = {
            "tokens": s_tokens,
            "actual_results": len(s_results),
            "tokens_per_result": round(s_tokens / max(len(s_results), 1)),
        }

        top_ids_n = [r["chunk_id"] for r in s_results]
        f_result = _fetch_docs(bench_db, top_ids_n)
        f_results = f_result.get("results", [])
        f_tokens = _response_tokens(f_result)
        response_data[f"full_n{n}"] = {
            "tokens": f_tokens,
            "actual_results": len(f_results),
            "tokens_per_result": round(f_tokens / max(len(f_results), 1)),
        }

    # Two-step progressive disclosure session via the public API.
    # Step 1 — broad summary scan
    step1 = _search_docs(bench_db, broad_query, limit=20)
    step1_tokens = _response_tokens(step1)
    top_ids = [r["chunk_id"] for r in step1.get("results", [])[:3]]

    # Step 2 — targeted full fetch of top 3 chunks
    step2 = _fetch_docs(bench_db, top_ids)
    step2_tokens = _response_tokens(step2)

    two_step_total = step1_tokens + step2_tokens
    naive_full = response_data["full_n20"]["tokens"]
    saving_pct = (
        round((naive_full - two_step_total) / naive_full * 100, 1)
        if naive_full
        else 0.0
    )

    results_payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "synd_version": synd.__version__,
        "token_counter": "len_div_4",
        "corpus": {
            "chunks": len(corpus_chunks),
            "avg_summary_chars": round(corpus_summary_chars / len(corpus_chunks)),
            "avg_content_chars": round(corpus_content_chars / len(corpus_chunks)),
        },
        "schema": schema,
        "responses": response_data,
        "progressive_disclosure": {
            "step1_summary_all_tokens": step1_tokens,
            "step2_full_top3_tokens": step2_tokens,
            "total_tokens": two_step_total,
            "vs_naive_full_n20_tokens": naive_full,
            "saving_pct": saving_pct,
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "latest.json"
    out_path.write_text(json.dumps(results_payload, indent=2))

    # Print summary for -s output
    print("\n── Synd MCP Token Overhead Benchmark ──────────────────────────")
    print(f"  git commit     : {results_payload['git_commit']}")
    print(f"  synd version   : {results_payload['synd_version']}")
    print(f"  token counter  : {results_payload['token_counter']} (approx ±15%)")
    print(
        f"\n  Corpus: {len(corpus_chunks)} chunks, "
        f"avg summary {results_payload['corpus']['avg_summary_chars']} chars, "
        f"avg content {results_payload['corpus']['avg_content_chars']} chars"
    )
    print("\n  Schema overhead")
    for t in schema["tools"]:
        print(f"    {t['name']:20s}  {t['tokens']:>5} tokens")
    print(
        f"    {'TOTAL':20s}  {schema['total_tokens']:>5} tokens  "
        f"({schema['pct_of_200k_context']}% of 200K ctx, "
        f"{schema['pct_of_128k_context']}% of 128K ctx)"
    )
    print("\n  Response sizes")
    print(f"    {'':20s}  {'tokens':>7}  {'tokens/result':>14}")
    for key, data in response_data.items():
        print(f"    {key:20s}  {data['tokens']:>7}  {data['tokens_per_result']:>14}")
    print("\n  Progressive disclosure (summary scan → targeted full fetch)")
    pd = results_payload["progressive_disclosure"]
    print(f"    step 1 (summary, all)    {pd['step1_summary_all_tokens']:>7} tokens")
    print(f"    step 2 (full, top 3)     {pd['step2_full_top3_tokens']:>7} tokens")
    print(f"    total                    {pd['total_tokens']:>7} tokens")
    print(f"    vs naive full (API max)  {pd['vs_naive_full_n20_tokens']:>7} tokens")
    print(f"    saving                   {pd['saving_pct']:>6}%")
    print(f"\n  Results written to {out_path}")
    print("────────────────────────────────────────────────────────────────\n")
