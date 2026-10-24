// HTTPS browser entry point. ORIGIN_URL and ALLOWED_ORIGINS are deployment bindings.
export async function proxy(request, env, fetchUpstream = fetch) {
  const url = new URL(request.url);
  if (url.pathname !== "/health" && !url.pathname.startsWith("/api/")) {
    return new Response("Not found", { status: 404 });
  }
  const allowed = new Set((env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean));
  const origin = request.headers.get("Origin");
  if (origin && !allowed.has(origin)) return new Response("Origin not allowed", { status: 403 });
  if (!["GET", "HEAD", "POST", "PUT", "OPTIONS"].includes(request.method)) {
    return new Response("Method not allowed", { status: 405 });
  }
  const cors = new Headers({ "Cache-Control": "no-store", Vary: "Origin" });
  if (origin) cors.set("Access-Control-Allow-Origin", origin);
  if (request.method === "OPTIONS") {
    cors.set("Access-Control-Allow-Methods", "GET, HEAD, POST, PUT, OPTIONS");
    cors.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
    return new Response(null, { status: 204, headers: cors });
  }
  const upstream = new URL(env.ORIGIN_URL);
  // Assign fields separately: a //host path must never replace the fixed origin.
  upstream.pathname = url.pathname;
  upstream.search = url.search;
  const headers = new Headers();
  for (const name of ["Content-Type", "Accept", "Authorization", "Origin"]) {
    if (request.headers.has(name)) headers.set(name, request.headers.get(name));
  }
  let body;
  if (!["GET", "HEAD"].includes(request.method)) {
    if (Number(request.headers.get("Content-Length") || 0) > 65536) {
      return new Response("Request too large", { status: 413 });
    }
    body = await request.arrayBuffer();
    if (body.byteLength > 65536) return new Response("Request too large", { status: 413 });
  }
  try {
    const result = await fetchUpstream(upstream, {
      method: request.method, headers, body, redirect: "manual", signal: AbortSignal.timeout(25000),
    });
    const responseHeaders = new Headers(result.headers);
    cors.forEach((value, key) => responseHeaders.set(key, value));
    const location = responseHeaders.get("Location");
    if (location && location.startsWith(upstream.origin + "/")) {
      responseHeaders.set("Location", url.origin + location.slice(upstream.origin.length));
    }
    return new Response(result.body, { status: result.status, headers: responseHeaders });
  } catch {
    return new Response('{"detail":"Backend temporarily unavailable"}', { status: 502, headers: cors });
  }
}

export default { fetch: (request, env) => proxy(request, env) };
