//! AN3's Rust shadow gateway.
//!
//! The gateway is deliberately a thin, staging-only reverse proxy.  The
//! existing Python service remains the source of truth for all requests and
//! data; Redis is only a best-effort cache for explicitly public static
//! responses.

use std::{
    collections::HashSet,
    env,
    net::SocketAddr,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use axum::{
    body::Body,
    extract::State,
    http::{
        header, HeaderMap, HeaderName, HeaderValue, Method, Request, StatusCode, Uri,
    },
    response::Response,
    routing::any,
    Router,
};
use redis::{aio::ConnectionManager, AsyncCommands};
use reqwest::{redirect::Policy, Client, Url};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tracing::{info, warn};

const CACHE_KEY_PREFIX: &str = "an3:rust-gateway:v1:";
const DEFAULT_CACHE_TTL_SECONDS: u64 = 60;
const MAX_CACHE_TTL_SECONDS: u64 = 300;
const DEFAULT_CACHE_MAX_BODY_BYTES: usize = 5 * 1024 * 1024;
const MAX_CACHE_MAX_BODY_BYTES: usize = 8 * 1024 * 1024;
const DEFAULT_CONNECT_TIMEOUT_SECONDS: u64 = 5;
const DEFAULT_HEALTH_TIMEOUT_SECONDS: u64 = 5;

/// Runtime configuration. Values are deliberately operational only; no
/// credential is stored in source or emitted by this service.
#[derive(Clone, Debug)]
pub struct GatewayConfig {
    pub bind_addr: SocketAddr,
    pub upstream: Url,
    pub redis_url: Option<String>,
    pub cache_ttl: Duration,
    pub cache_max_body_bytes: usize,
    pub connect_timeout: Duration,
    pub health_timeout: Duration,
}

impl GatewayConfig {
    /// Reads configuration without supplying a default upstream. Requiring an
    /// explicit upstream prevents an accidental proxy to a production target.
    pub fn from_env() -> Result<Self, String> {
        let bind_addr = env::var("AN3_GATEWAY_BIND")
            .unwrap_or_else(|_| "0.0.0.0:8093".to_owned())
            .parse::<SocketAddr>()
            .map_err(|_| "AN3_GATEWAY_BIND must be an IP address and port".to_owned())?;

        let upstream_raw = env::var("AN3_GATEWAY_UPSTREAM")
            .map_err(|_| "AN3_GATEWAY_UPSTREAM is required".to_owned())?;
        let upstream = Url::parse(&upstream_raw)
            .map_err(|_| "AN3_GATEWAY_UPSTREAM must be an absolute HTTP(S) URL".to_owned())?;
        if !matches!(upstream.scheme(), "http" | "https")
            || upstream.query().is_some()
            || upstream.fragment().is_some()
        {
            return Err(
                "AN3_GATEWAY_UPSTREAM must be an HTTP(S) origin or path without query/fragment"
                    .to_owned(),
            );
        }

        let redis_url = env::var("AN3_GATEWAY_REDIS_URL")
            .ok()
            .filter(|value| !value.trim().is_empty());

        Ok(Self {
            bind_addr,
            upstream,
            redis_url,
            cache_ttl: Duration::from_secs(read_bounded_u64(
                "AN3_GATEWAY_CACHE_TTL_SECONDS",
                DEFAULT_CACHE_TTL_SECONDS,
                1,
                MAX_CACHE_TTL_SECONDS,
            )?),
            cache_max_body_bytes: read_bounded_u64(
                "AN3_GATEWAY_CACHE_MAX_BODY_BYTES",
                DEFAULT_CACHE_MAX_BODY_BYTES as u64,
                1,
                MAX_CACHE_MAX_BODY_BYTES as u64,
            )? as usize,
            connect_timeout: Duration::from_secs(read_bounded_u64(
                "AN3_GATEWAY_CONNECT_TIMEOUT_SECONDS",
                DEFAULT_CONNECT_TIMEOUT_SECONDS,
                1,
                30,
            )?),
            health_timeout: Duration::from_secs(read_bounded_u64(
                "AN3_GATEWAY_HEALTH_TIMEOUT_SECONDS",
                DEFAULT_HEALTH_TIMEOUT_SECONDS,
                1,
                30,
            )?),
        })
    }
}

fn read_bounded_u64(name: &str, default: u64, minimum: u64, maximum: u64) -> Result<u64, String> {
    let value = match env::var(name) {
        Ok(raw) => raw
            .parse::<u64>()
            .map_err(|_| format!("{name} must be a whole number"))?,
        Err(_) => default,
    };
    if !(minimum..=maximum).contains(&value) {
        return Err(format!("{name} must be between {minimum} and {maximum}"));
    }
    Ok(value)
}

#[derive(Clone)]
pub struct AppState {
    config: Arc<GatewayConfig>,
    client: Client,
    cache: Option<ConnectionManager>,
}

impl AppState {
    pub async fn new(config: GatewayConfig) -> Self {
        let client = Client::builder()
            // Redirects belong to the legacy app and must reach the browser
            // unchanged rather than being followed by the gateway.
            .redirect(Policy::none())
            // Do not set a total request timeout: uploads and ROM downloads
            // may legitimately run for longer than a small HTTP timeout.
            .connect_timeout(config.connect_timeout)
            .tcp_keepalive(Some(Duration::from_secs(60)))
            .build()
            .expect("the static HTTP client configuration is valid");

        let cache = match config.redis_url.as_deref() {
            Some(redis_url) => match redis::Client::open(redis_url) {
                Ok(client) => match ConnectionManager::new(client).await {
                    Ok(connection) => {
                        info!("Redis cache connection is available");
                        Some(connection)
                    }
                    Err(_) => {
                        // Redis is a performance optimization only. Keep the
                        // proxy online if it has not started yet.
                        warn!("Redis cache is unavailable at startup; continuing without cache");
                        None
                    }
                },
                Err(_) => {
                    warn!("Redis cache configuration is invalid; continuing without cache");
                    None
                }
            },
            None => {
                warn!("Redis cache is not configured; continuing without cache");
                None
            }
        };

        Self {
            config: Arc::new(config),
            client,
            cache,
        }
    }
}

/// Builds a router which intentionally has no application routes of its own:
/// every request goes to the configured legacy upstream.
pub fn app(state: AppState) -> Router {
    Router::new()
        .route("/", any(proxy_handler))
        .route("/*path", any(proxy_handler))
        .with_state(state)
}

async fn proxy_handler(State(state): State<AppState>, request: Request<Body>) -> Response {
    let (parts, body) = request.into_parts();
    let is_health = parts.uri.path() == "/health";
    let cache_candidate = request_can_use_cache(&parts.method, &parts.uri, &parts.headers);
    let cache_key = cache_candidate.then(|| cache_key(&state.config, &parts.uri));

    // A cache hit is only possible for a body-less GET. This avoids dropping a
    // meaningful GET payload while still allowing safe browser asset requests.
    if let Some(key) = cache_key.as_deref() {
        if let Some(cached) = cache_get(&state, key).await {
            if let Some(response) = response_from_cached(cached, CacheDisposition::Hit, false) {
                return response;
            }
        }
    }

    let upstream_url = match upstream_url(&state.config.upstream, &parts.uri) {
        Ok(url) => url,
        Err(()) => return gateway_error(StatusCode::BAD_GATEWAY, "invalid upstream request"),
    };

    let has_body = request_may_have_body(&parts.method, &parts.headers);
    let mut upstream_request = state
        .client
        .request(parts.method.clone(), upstream_url)
        .headers(forward_request_headers(&parts.headers));
    if has_body {
        upstream_request = upstream_request.body(reqwest::Body::wrap_stream(body.into_data_stream()));
    }

    // `/health` must report the state of the Python service, not merely that
    // this process is listening. Its bounded timeout intentionally applies only
    // to this small health request, not to uploads or game downloads.
    let upstream_response = if is_health {
        match tokio::time::timeout(state.config.health_timeout, upstream_request.send()).await {
            Ok(result) => result,
            Err(_) => return gateway_unavailable(),
        }
    } else {
        upstream_request.send().await
    };

    let upstream_response = match upstream_response {
        Ok(response) => response,
        Err(_) => return gateway_unavailable(),
    };

    let status = upstream_response.status();
    let headers = forward_response_headers(upstream_response.headers());
    let cache_ttl = cache_candidate.then(|| {
        response_cache_ttl(
            status,
            &headers,
            state.config.cache_max_body_bytes,
            state.config.cache_ttl,
        )
    });

    if let Some(cache_ttl) = cache_ttl.flatten() {
        // A cacheable response is required to carry a bounded Content-Length.
        // This preserves streaming for unknown/large responses and bounds the
        // memory and Redis footprint used by this optional optimization.
        match upstream_response.bytes().await {
            Ok(body) => {
                if body.len() <= state.config.cache_max_body_bytes {
                    let cached = CachedResponse::from_parts(status, &headers, body.to_vec());
                    if let Some(key) = cache_key.as_deref() {
                        cache_set(&state, key, &cached, cache_ttl).await;
                    }
                    return response_from_cached(cached, CacheDisposition::Miss, is_health)
                        .expect("a freshly built cached response is valid");
                }
                return response_from_parts(status, headers, Body::from(body), CacheDisposition::Bypass, is_health);
            }
            Err(_) => return gateway_unavailable(),
        }
    }

    response_from_parts(
        status,
        headers,
        Body::from_stream(upstream_response.bytes_stream()),
        CacheDisposition::Bypass,
        is_health,
    )
}

fn request_may_have_body(method: &Method, headers: &HeaderMap) -> bool {
    if method != Method::GET && method != Method::HEAD {
        return true;
    }

    headers
        .get(header::CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.trim() != "0")
        || headers.contains_key(header::TRANSFER_ENCODING)
}

/// Cache only anonymous, ordinary GETs to a small public allowlist. The
/// response is subsequently checked for explicit public cache headers.
pub fn request_can_use_cache(method: &Method, uri: &Uri, headers: &HeaderMap) -> bool {
    if method != Method::GET || request_may_have_body(method, headers) {
        return false;
    }
    if headers.contains_key(header::COOKIE)
        || headers.contains_key(header::AUTHORIZATION)
        || headers.contains_key(header::PROXY_AUTHORIZATION)
        || headers.contains_key(header::RANGE)
        || headers.contains_key(header::IF_RANGE)
        || headers.contains_key(header::IF_MATCH)
        || headers.contains_key(header::IF_NONE_MATCH)
        || headers.contains_key(header::IF_MODIFIED_SINCE)
        || headers.contains_key(header::IF_UNMODIFIED_SINCE)
    {
        return false;
    }
    if request_cache_control_bypasses(headers) {
        return false;
    }

    let path = uri.path();
    // These prefixes must stay outside Redis even if a future app route emits
    // permissive cache headers by mistake.
    if path.starts_with("/admin")
        || path.starts_with("/api/")
        || path.starts_with("/upload")
        || path.starts_with("/download/")
        || path.starts_with("/game-file/")
        || path.starts_with("/emulatorjs/")
        || path.starts_with("/custom/")
        || path.starts_with("/play/")
        || path.starts_with("/offline")
        || path.starts_with("/core-preload/")
        || path.starts_with("/account")
        || path.starts_with("/login")
        || path.starts_with("/register")
        || path == "/health"
    {
        return false;
    }

    path == "/"
        || path.starts_with("/game/")
        || path.starts_with("/static/")
        || path.starts_with("/cover/")
        || path.starts_with("/screenshot/")
}

fn request_cache_control_bypasses(headers: &HeaderMap) -> bool {
    // The gateway deliberately does not implement HTTP revalidation itself.
    // Let the legacy server evaluate every explicit client cache directive.
    headers.contains_key(header::CACHE_CONTROL) || headers.contains_key("pragma")
}

/// Returns the effective Redis TTL only for an explicitly public, bounded
/// upstream response. `s-maxage` takes precedence because Redis is shared;
/// the value is also reduced by any upstream `Age` before applying the local
/// maximum.
fn response_cache_ttl(
    status: StatusCode,
    headers: &HeaderMap,
    maximum_body_bytes: usize,
    configured_ttl: Duration,
) -> Option<Duration> {
    if status != StatusCode::OK
        || headers.contains_key(header::SET_COOKIE)
        || headers.contains_key(header::CONTENT_RANGE)
        || headers.contains_key(header::VARY)
    {
        return None;
    }

    let mut is_public = false;
    let mut max_age = None;
    let mut shared_max_age = None;
    for cache_control in headers
        .get_all(header::CACHE_CONTROL)
        .iter()
        .filter_map(|value| value.to_str().ok())
    {
        for raw_directive in cache_control.split(',') {
            let (name, value) = raw_directive
                .trim()
                .split_once('=')
                .map(|(name, value)| (name.trim().to_ascii_lowercase(), Some(value.trim())))
                .unwrap_or_else(|| (raw_directive.trim().to_ascii_lowercase(), None));
            match name.as_str() {
                "public" => is_public = true,
                "private" | "no-cache" | "no-store" => return None,
                "max-age" => max_age = value.and_then(parse_cache_seconds),
                "s-maxage" => shared_max_age = value.and_then(parse_cache_seconds),
                _ => {}
            }
        }
    }
    if !is_public {
        return None;
    }

    let upstream_ttl = shared_max_age.or(max_age)?;
    let age = match headers.get(header::AGE) {
        Some(value) => value.to_str().ok().and_then(parse_cache_seconds)?,
        None => 0,
    };
    let remaining_ttl = upstream_ttl.checked_sub(age)?;
    if remaining_ttl == 0 {
        return None;
    }

    let Some(length) = headers
        .get(header::CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<usize>().ok())
    else {
        return None;
    };
    if length > maximum_body_bytes {
        return None;
    }

    let content_type_is_safe = headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(is_cacheable_content_type);
    content_type_is_safe.then(|| configured_ttl.min(Duration::from_secs(remaining_ttl)))
}

fn parse_cache_seconds(value: &str) -> Option<u64> {
    value.trim_matches('"').parse::<u64>().ok()
}

fn is_cacheable_content_type(content_type: &str) -> bool {
    let media_type = content_type
        .split(';')
        .next()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    media_type.starts_with("text/")
        || media_type.starts_with("image/")
        || media_type.starts_with("font/")
        || matches!(
            media_type.as_str(),
            "application/javascript"
                | "application/x-javascript"
                | "application/json"
                | "application/manifest+json"
                | "application/wasm"
                | "application/font-woff"
                | "application/font-woff2"
                | "application/vnd.ms-fontobject"
        )
}

fn cache_key(config: &GatewayConfig, uri: &Uri) -> String {
    let path_and_query = uri.path_and_query().map(|value| value.as_str()).unwrap_or("/");
    let mut hasher = Sha256::new();
    // Hash the upstream too so a shared Redis instance cannot serve content
    // from another configured target. The resulting key does not expose the
    // configured URL.
    hasher.update(config.upstream.as_str().as_bytes());
    hasher.update(b"\nGET\n");
    hasher.update(path_and_query.as_bytes());
    format!("{CACHE_KEY_PREFIX}{}", hex::encode(hasher.finalize()))
}

#[derive(Debug, Serialize, Deserialize)]
struct CachedResponse {
    status: u16,
    headers: Vec<(String, Vec<u8>)>,
    body: Vec<u8>,
    cached_at_unix_seconds: u64,
}

impl CachedResponse {
    fn from_parts(status: StatusCode, headers: &HeaderMap, body: Vec<u8>) -> Self {
        Self {
            status: status.as_u16(),
            headers: headers
                .iter()
                .map(|(name, value)| (name.as_str().to_owned(), value.as_bytes().to_vec()))
                .collect(),
            body,
            cached_at_unix_seconds: unix_seconds_now(),
        }
    }
}

fn unix_seconds_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

async fn cache_get(state: &AppState, key: &str) -> Option<CachedResponse> {
    let mut connection = state.cache.clone()?;
    let value: redis::RedisResult<Option<Vec<u8>>> = connection.get(key).await;
    match value {
        Ok(Some(payload)) => match bincode::deserialize::<CachedResponse>(&payload) {
            Ok(cached) => Some(cached),
            Err(_) => {
                // A corrupt cache entry is treated as a miss. Do not make a
                // user request depend on cache repair or cache availability.
                warn!("Ignoring an unreadable Redis cache entry");
                None
            }
        },
        Ok(None) => None,
        Err(_) => {
            warn!("Redis cache read failed; proxying without cache");
            None
        }
    }
}

async fn cache_set(state: &AppState, key: &str, cached: &CachedResponse, ttl: Duration) {
    let Some(mut connection) = state.cache.clone() else {
        return;
    };
    let payload = match bincode::serialize(cached) {
        Ok(payload) => payload,
        Err(_) => {
            warn!("Could not serialize a Redis cache entry");
            return;
        }
    };
    let ttl_seconds = ttl.as_secs().max(1);
    let result: redis::RedisResult<()> = connection.set_ex(key, payload, ttl_seconds).await;
    if result.is_err() {
        warn!("Redis cache write failed; response was still proxied");
    }
}

#[derive(Clone, Copy)]
enum CacheDisposition {
    Hit,
    Miss,
    Bypass,
}

impl CacheDisposition {
    fn header_value(self) -> HeaderValue {
        match self {
            Self::Hit => HeaderValue::from_static("HIT"),
            Self::Miss => HeaderValue::from_static("MISS"),
            Self::Bypass => HeaderValue::from_static("BYPASS"),
        }
    }
}

fn response_from_cached(
    cached: CachedResponse,
    disposition: CacheDisposition,
    is_health: bool,
) -> Option<Response> {
    response_from_cached_at(cached, disposition, is_health, unix_seconds_now())
}

fn response_from_cached_at(
    cached: CachedResponse,
    disposition: CacheDisposition,
    is_health: bool,
    now_unix_seconds: u64,
) -> Option<Response> {
    let status = StatusCode::from_u16(cached.status).ok()?;
    let cached_at_unix_seconds = cached.cached_at_unix_seconds;
    let mut headers = HeaderMap::new();
    for (name, value) in cached.headers {
        let name = HeaderName::from_bytes(name.as_bytes()).ok()?;
        let value = HeaderValue::from_bytes(&value).ok()?;
        headers.append(name, value);
    }
    if let CacheDisposition::Hit = disposition {
        // Keep the legacy Cache-Control contract meaningful to downstream
        // clients: a Redis hit has already aged since the upstream response
        // was received, so update rather than replay the stored Age value.
        let original_age = headers
            .get(header::AGE)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(0);
        let elapsed_seconds = now_unix_seconds.saturating_sub(cached_at_unix_seconds);
        let age = original_age.saturating_add(elapsed_seconds).to_string();
        let age = HeaderValue::from_bytes(age.as_bytes()).ok()?;
        headers.insert(header::AGE, age);
    }
    Some(response_from_parts(
        status,
        headers,
        Body::from(cached.body),
        disposition,
        is_health,
    ))
}

fn response_from_parts(
    status: StatusCode,
    mut headers: HeaderMap,
    body: Body,
    disposition: CacheDisposition,
    is_health: bool,
) -> Response {
    headers.insert("x-an3-gateway", HeaderValue::from_static("rust-shadow"));
    headers.insert("x-an3-gateway-cache", disposition.header_value());
    if is_health {
        headers.insert(
            "x-an3-gateway-upstream",
            HeaderValue::from_static("reachable"),
        );
    }

    let mut response = Response::new(body);
    *response.status_mut() = status;
    *response.headers_mut() = headers;
    response
}

fn gateway_unavailable() -> Response {
    let mut response = gateway_error(StatusCode::SERVICE_UNAVAILABLE, "legacy upstream unavailable");
    response.headers_mut().insert(
        "x-an3-gateway-upstream",
        HeaderValue::from_static("unavailable"),
    );
    response
}

fn gateway_error(status: StatusCode, message: &str) -> Response {
    let payload = serde_json::json!({"ok": false, "error": message}).to_string();
    let mut response = Response::new(Body::from(payload));
    *response.status_mut() = status;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json; charset=utf-8"),
    );
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response.headers_mut().insert(
        "x-an3-gateway",
        HeaderValue::from_static("rust-shadow"),
    );
    response
        .headers_mut()
        .insert("x-an3-gateway-cache", HeaderValue::from_static("BYPASS"));
    response
}

fn upstream_url(base: &Url, uri: &Uri) -> Result<Url, ()> {
    let path_and_query = uri.path_and_query().map(|value| value.as_str()).unwrap_or("/");
    let base = base.as_str().trim_end_matches('/');
    Url::parse(&format!("{base}{path_and_query}")).map_err(|_| ())
}

/// Copies all end-to-end headers. HTTP hop-by-hop and `Host` headers cannot be
/// forwarded by a compliant reverse proxy; reqwest creates the upstream Host.
fn forward_request_headers(headers: &HeaderMap) -> HeaderMap {
    let mut forwarded = copy_end_to_end_headers(headers);
    forwarded.remove(header::HOST);
    if !forwarded.contains_key("x-forwarded-host") {
        if let Some(host) = headers.get(header::HOST) {
            forwarded.insert("x-forwarded-host", host.clone());
        }
    }
    if !forwarded.contains_key("x-forwarded-proto") {
        forwarded.insert("x-forwarded-proto", HeaderValue::from_static("http"));
    }
    forwarded
}

fn forward_response_headers(headers: &HeaderMap) -> HeaderMap {
    copy_end_to_end_headers(headers)
}

fn copy_end_to_end_headers(headers: &HeaderMap) -> HeaderMap {
    let connection_headers = connection_header_names(headers);
    let mut forwarded = HeaderMap::new();
    for (name, value) in headers {
        if !is_hop_by_hop(name, &connection_headers) {
            forwarded.append(name.clone(), value.clone());
        }
    }
    forwarded
}

fn connection_header_names(headers: &HeaderMap) -> HashSet<HeaderName> {
    headers
        .get_all(header::CONNECTION)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(|value| value.split(','))
        .filter_map(|name| HeaderName::from_bytes(name.trim().as_bytes()).ok())
        .collect()
}

fn is_hop_by_hop(name: &HeaderName, connection_headers: &HashSet<HeaderName>) -> bool {
    connection_headers.contains(name)
        || matches!(
            name.as_str(),
            "connection"
                | "keep-alive"
                | "proxy-authenticate"
                | "proxy-authorization"
                | "te"
                | "trailer"
                | "transfer-encoding"
                | "upgrade"
        )
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use axum::{
        body::{to_bytes, Body},
        http::{header, HeaderValue, Request, Response, StatusCode},
        routing::any,
        Router,
    };
    use reqwest::Url;
    use tokio::net::TcpListener;
    use tower::ServiceExt;

    use super::*;

    fn test_config(upstream: Url) -> GatewayConfig {
        GatewayConfig {
            bind_addr: "127.0.0.1:0".parse().unwrap(),
            upstream,
            redis_url: None,
            cache_ttl: Duration::from_secs(10),
            cache_max_body_bytes: 1024,
            connect_timeout: Duration::from_secs(2),
            health_timeout: Duration::from_secs(2),
        }
    }

    #[test]
    fn cache_policy_excludes_sensitive_and_dynamic_routes() {
        let headers = HeaderMap::new();
        for path in [
            "/admin",
            "/admin/api/games/1",
            "/api/library-version",
            "/upload/chunk",
            "/download/game/example",
            "/game-file/example/rom",
            "/emulatorjs/stable/data/core.wasm",
            "/custom/1/index.html",
            "/play/example",
            "/offline",
            "/core-preload/gba",
            "/account",
            "/login",
            "/register",
            "/health",
        ] {
            let uri: Uri = path.parse().unwrap();
            assert!(!request_can_use_cache(&Method::GET, &uri, &headers), "{path}");
        }

        for path in ["/static/site.css", "/cover/1", "/screenshot/1"] {
            let uri: Uri = path.parse().unwrap();
            assert!(request_can_use_cache(&Method::GET, &uri, &headers), "{path}");
        }
    }

    #[test]
    fn cache_policy_requires_anonymous_bodyless_get_without_range() {
        let uri: Uri = "/static/site.css".parse().unwrap();
        let mut headers = HeaderMap::new();
        headers.insert(header::COOKIE, HeaderValue::from_static("an3_session=x"));
        assert!(!request_can_use_cache(&Method::GET, &uri, &headers));

        headers.clear();
        headers.insert(header::RANGE, HeaderValue::from_static("bytes=0-3"));
        assert!(!request_can_use_cache(&Method::GET, &uri, &headers));

        headers.clear();
        headers.insert(header::CONTENT_LENGTH, HeaderValue::from_static("2"));
        assert!(!request_can_use_cache(&Method::GET, &uri, &headers));

        headers.clear();
        headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
        assert!(!request_can_use_cache(&Method::GET, &uri, &headers));

        headers.clear();
        headers.insert(header::IF_NONE_MATCH, HeaderValue::from_static("\"asset\""));
        assert!(!request_can_use_cache(&Method::GET, &uri, &headers));
    }

    #[test]
    fn cache_policy_requires_an_explicit_public_bounded_response() {
        let mut headers = HeaderMap::new();
        headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("public, max-age=60"));
        headers.insert(header::CONTENT_LENGTH, HeaderValue::from_static("12"));
        headers.insert(header::CONTENT_TYPE, HeaderValue::from_static("text/css"));
        assert_eq!(
            response_cache_ttl(StatusCode::OK, &headers, 128, Duration::from_secs(120)),
            Some(Duration::from_secs(60))
        );

        headers.insert(header::SET_COOKIE, HeaderValue::from_static("an3_session=x"));
        assert_eq!(
            response_cache_ttl(StatusCode::OK, &headers, 128, Duration::from_secs(120)),
            None
        );
    }

    #[test]
    fn cache_ttl_never_exceeds_remaining_upstream_freshness() {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::CACHE_CONTROL,
            HeaderValue::from_static("public, max-age=120, s-maxage=12"),
        );
        headers.insert(header::AGE, HeaderValue::from_static("2"));
        headers.insert(header::CONTENT_LENGTH, HeaderValue::from_static("12"));
        headers.insert(header::CONTENT_TYPE, HeaderValue::from_static("application/json"));
        assert_eq!(
            response_cache_ttl(StatusCode::OK, &headers, 128, Duration::from_secs(60)),
            Some(Duration::from_secs(10))
        );
    }

    #[test]
    fn cached_hit_advances_upstream_age_deterministically() {
        let cached = CachedResponse {
            status: StatusCode::OK.as_u16(),
            headers: vec![
                ("age".to_owned(), b"2".to_vec()),
                ("content-type".to_owned(), b"text/css".to_vec()),
                ("content-length".to_owned(), b"2".to_vec()),
            ],
            body: b"{}".to_vec(),
            cached_at_unix_seconds: 1_000,
        };

        let response = response_from_cached_at(cached, CacheDisposition::Hit, false, 1_007)
            .unwrap();
        assert_eq!(response.headers().get(header::AGE).unwrap(), "9");
        assert_eq!(
            response.headers().get("x-an3-gateway-cache").unwrap(),
            "HIT"
        );
    }

    async fn echo_upstream(request: Request<Body>) -> Response<Body> {
        let method = request.method().to_string();
        let query = request.uri().query().unwrap_or("none").to_owned();
        let range = request
            .headers()
            .get(header::RANGE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or("none")
            .to_owned();
        let forwarded = request
            .headers()
            .get("x-test-proxy")
            .and_then(|value| value.to_str().ok())
            .unwrap_or("missing")
            .to_owned();
        let body = to_bytes(request.into_body(), 1024 * 1024).await.unwrap();
        let mut response = Response::new(Body::from(format!(
            "method={method};query={query};range={range};header={forwarded};body={}",
            String::from_utf8_lossy(&body)
        )));
        response.headers_mut().insert(
            header::CACHE_CONTROL,
            HeaderValue::from_static("no-store"),
        );
        response.headers_mut().append(
            header::SET_COOKIE,
            HeaderValue::from_static("legacy_one=1; Path=/; HttpOnly"),
        );
        response.headers_mut().append(
            header::SET_COOKIE,
            HeaderValue::from_static("legacy_two=2; Path=/; SameSite=Lax"),
        );
        if range != "none" {
            *response.status_mut() = StatusCode::PARTIAL_CONTENT;
            response.headers_mut().insert(
                header::CONTENT_RANGE,
                HeaderValue::from_static("bytes 10-19/100"),
            );
        }
        response
    }

    async fn test_upstream() -> Url {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new().fallback(echo_upstream);
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        Url::parse(&format!("http://{address}")).unwrap()
    }

    #[tokio::test]
    async fn proxy_preserves_post_body_and_end_to_end_headers() {
        let state = AppState::new(test_config(test_upstream().await)).await;
        let response = app(state)
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/example?source=test")
                    .header("x-test-proxy", "kept")
                    .body(Body::from("payload"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers().get_all(header::SET_COOKIE).iter().count(), 2);
        let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
        assert_eq!(
            String::from_utf8(body.to_vec()).unwrap(),
            "method=POST;query=source=test;range=none;header=kept;body=payload"
        );
    }

    #[tokio::test]
    async fn proxy_forwards_ranges_without_cache() {
        let state = AppState::new(test_config(test_upstream().await)).await;
        let response = app(state)
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/game-file/example/rom")
                    .header(header::RANGE, "bytes=10-19")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::PARTIAL_CONTENT);
        assert_eq!(response.headers().get(header::CONTENT_RANGE).unwrap(), "bytes 10-19/100");
        assert_eq!(
            response
                .headers()
                .get("x-an3-gateway-cache")
                .unwrap(),
            "BYPASS"
        );
        let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
        assert!(String::from_utf8_lossy(&body).contains("range=bytes=10-19"));
    }

    #[tokio::test]
    async fn health_response_is_the_upstream_response() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let upstream = Router::new().route(
            "/health",
            any(|| async {
                let mut response = Response::new(Body::from(r#"{"ok":true,"asset_version":"test"}"#));
                response.headers_mut().insert(
                    header::CONTENT_TYPE,
                    HeaderValue::from_static("application/json"),
                );
                response
            }),
        );
        tokio::spawn(async move {
            axum::serve(listener, upstream).await.unwrap();
        });

        let state = AppState::new(test_config(
            Url::parse(&format!("http://{address}")).unwrap(),
        ))
        .await;
        let response = app(state)
            .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers().get("x-an3-gateway-upstream").unwrap(), "reachable");
        let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
        assert_eq!(body.as_ref(), br#"{"ok":true,"asset_version":"test"}"#);
    }
}
