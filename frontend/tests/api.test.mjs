import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "../src/api.ts";

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
