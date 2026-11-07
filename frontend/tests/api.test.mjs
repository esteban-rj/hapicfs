import { test } from "node:test";
import assert from "node:assert/strict";
import { api, ApiError } from "../src/api.ts";

test("plain-text server failures produce a useful message without exposing the response", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("Internal Server Error: private server details", { status: 500, headers: { "Content-Type": "text/plain" } }));
  await assert.rejects(api("/bootstrap"), error => {
    assert.equal(error.message, "Ocurrió un error interno en el servidor. Recarga la página o vuelve a intentarlo.");
    assert.ok(!error.message.includes("Unexpected token"));
    assert.ok(!error.message.includes("private server details"));
    return true;
  });
});

test("invalid successful responses are identified without a JSON parsing exception", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("<html>Unexpected proxy page</html>", { status: 200 }));
  await assert.rejects(api("/state"), { message: "El servidor devolvió una respuesta no válida. Recarga la página." });
});

test("JSON validation errors retain the explanation from the server", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Nombre obligatorio." }, { status: 400 }));
  await assert.rejects(api("/organizations"), { message: "Nombre obligatorio." });
});

test("valid API responses still load the workspace", async t => {
  const state = { organizations: [], projects: [], agents: [] };
  t.mock.method(globalThis, "fetch", async () => Response.json(state));
  assert.deepEqual(await api("/state"), state);
});

test("expired sessions notify the login screen even when a proxy returns a non-JSON error", async t => {
  globalThis.window = new EventTarget();
  t.after(() => { delete globalThis.window; });
  let expired = false;
  window.addEventListener("hapic:unauthorized", () => { expired = true; });
  t.mock.method(globalThis, "fetch", async () => new Response("Unauthorized", { status: 401 }));
  await assert.rejects(api("/state"), error => error instanceof ApiError && error.status === 401);
  assert.equal(expired, true);
});
