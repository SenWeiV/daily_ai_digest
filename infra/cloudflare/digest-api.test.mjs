import test from "node:test";
import assert from "node:assert/strict";
import { proxy } from "./digest-api.mjs";

const env = { ORIGIN_URL: "https://backend.example", ALLOWED_ORIGINS: "https://dashboard.example" };
test("proxy retains fixed origin, query and body", async () => {
  const request = new Request("https://edge.example/api/digest/trigger?digest_type=weekly", {
    method: "POST", headers: { Origin: "https://dashboard.example", "Content-Type": "application/json" }, body: '{"send_email":false}',
  });
  const response = await proxy(request, env, async (url, options) => {
    assert.equal(url.origin, env.ORIGIN_URL);
    assert.equal(url.searchParams.get("digest_type"), "weekly");
    assert.equal(new TextDecoder().decode(options.body), '{"send_email":false}');
    return new Response('{"success":true}', { headers: { "Content-Type": "application/json" } });
  });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), "https://dashboard.example");
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});
test("preflight works and unapproved origins and paths are rejected", async () => {
  const noFetch = () => { throw new Error("must not reach upstream"); };
  assert.equal((await proxy(new Request("https://edge.example/api/status", { method: "OPTIONS", headers: { Origin: "https://dashboard.example" } }), env, noFetch)).status, 204);
  assert.equal((await proxy(new Request("https://edge.example/api/status", { headers: { Origin: "https://other.example" } }), env, noFetch)).status, 403);
  assert.equal((await proxy(new Request("https://edge.example//other.example"), env, noFetch)).status, 404);
});
test("backend redirects stay on HTTPS and errors hide origin details", async () => {
  const req = new Request("https://edge.example/api/status/");
  const redirect = await proxy(req, env, async () => new Response(null, { status: 307, headers: { Location: env.ORIGIN_URL + "/api/status" } }));
  assert.equal(redirect.headers.get("Location"), "https://edge.example/api/status");
  const failed = await proxy(req, env, async () => { throw new Error("private network detail"); });
  assert.equal(failed.status, 502);
  assert.ok(!(await failed.text()).includes(env.ORIGIN_URL));
});
