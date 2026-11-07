import { test } from "node:test";
import assert from "node:assert/strict";
import { officeLayout, officeMembers, officePresence } from "../src/officeModel.ts";

const project = { id: "project-a", organization_id: "org-a", name: "Proyecto A" };
const agent = (overrides = {}) => ({ id: "ux-a", name: "UX", kind: "ux", project_id: "project-a", organization_id: "org-a", status: "running", created_at: "2026-11-07", ...overrides });
const idle = { busy: false, active_tasks: 0, queued_tasks: 0, tasks: [] };

test("each office excludes agents from other projects and organizations", () => {
  const roster = [agent(), agent({ id: "outside-project", project_id: "project-b" }), agent({ id: "outside-org", organization_id: "org-b" }), agent({ id: "hapic-a", kind: "hapic" })];
  assert.deepEqual(officeMembers(project, roster).map(a => a.id), ["hapic-a", "ux-a"]);
  assert.equal(roster[0].id, "ux-a", "the shared roster remains untouched");
});

test("layout grows to give every real agent a separate desk inside the office", () => {
  for (const count of [0, 1, 6, 13, 40]) {
    const { width, depth, seats } = officeLayout(count);
    assert.equal(seats.length, count);
    assert.equal(new Set(seats.map(p => `${p.x},${p.z}`)).size, count);
    for (const seat of seats) {
      assert.ok(seat.x - 1 > -width / 2 && seat.x + 1 < width / 2 - 4, "desks fit without entering the lounge");
      assert.ok(seat.z - 1 > -depth / 2 && seat.z + 1.5 < depth / 2, "desks fit inside the room");
    }
  }
});

test("a running runtime or an unconfirmed task never pretends to be working", () => {
  assert.equal(officePresence(agent()).label, "Sin confirmar");
  assert.equal(officePresence(agent(), idle).working, false);
  const interrupted = { ...idle, tasks: [{ agent_id: "ux-a", state: "running", executing: false, objective: "Propuesta UX" }] };
  assert.equal(officePresence(agent(), interrupted).label, "Revisar ejecución");
  assert.equal(officePresence(agent(), interrupted).working, false);
});

test("only confirmed execution animates the assigned agent", () => {
  const active = { ...idle, busy: true, tasks: [{ agent_id: "ux-a", state: "running", executing: true, objective: "Propuesta UX" }] };
  assert.equal(officePresence(agent(), active).working, true);
  assert.equal(officePresence(agent(), active).detail, "Propuesta UX");
  assert.equal(officePresence(agent({ id: "another" }), active).working, false);
  assert.equal(officePresence(agent({ id: "hapic-a", kind: "hapic" }), active).working, true);
});

test("queued work and stopped runtimes retain their actual states", () => {
  assert.equal(officePresence(agent({ status: "stopped" }), idle).label, "Runtime sin iniciar");
  assert.equal(officePresence(agent({ status: "blocked" }), idle).label, "Requiere configuración");
  const queued = { ...idle, tasks: [{ agent_id: "ux-a", state: "queued", executing: false, objective: "Propuesta UX" }] };
  assert.equal(officePresence(agent(), queued).label, "En cola");
  assert.equal(officePresence(agent(), queued).working, false);
});
