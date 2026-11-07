import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page) {
  const bootstrap = await page.request.post("/api/auth/login", { data: {
    username: process.env.HAPIC_TEST_LOGIN_USERNAME || "office-test-user",
    password: process.env.HAPIC_TEST_LOGIN_PASSWORD || "office-browser-test-password",
  } });
  expect(bootstrap.ok()).toBeTruthy();
  const { csrf } = await bootstrap.json();
  const create = async (url: string, data: object) => {
    const response = await page.request.post(url, { data, headers: { "X-Hapic-CSRF": csrf } });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const org = await create("/api/organizations", { name: "Oficinas QA " + Date.now() });
  const first = await create(`/api/organizations/${org.id}/projects`, { name: "Estudio Aurora" });
  const second = await create(`/api/organizations/${org.id}/projects`, { name: "Proyecto Boreal" });
  const planner = await create(`/api/projects/${first.id}/agents`, { name: "Atlas", template: "architect" });
  const coder = await create(`/api/projects/${first.id}/agents`, { name: "Nico", template: "coder", planner_id: planner.id });
  for (const [name, template] of [["Cata", "ux"], ["Vale", "graphic-designer"], ["Pipe", "community-manager"]]) await create(`/api/projects/${first.id}/agents`, { name, template });
  await create(`/api/projects/${second.id}/agents`, { name: "Solo Boreal", template: "ux" });
  await page.goto("/");
  await page.getByLabel("Organización activa").selectOption(org.id);
  await page.getByRole("navigation").getByRole("button", { name: "Proyectos", exact: true }).click();
  return { first, second, coder };
}

test("offices load only on request, isolate the roster, and navigate to the real chat", async ({ page }) => {
  const errors: string[] = [];
  const officeRequests: string[] = [];
  const mutations: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => {
    if (request.url().includes("/assets/ProjectOffice-")) officeRequests.push(request.url());
    if (/\/(start|chat)$/.test(request.url()) && request.method() === "POST") mutations.push(request.url());
  });
  const { coder } = await setup(page);
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(officeRequests).toHaveLength(0);
  await page.getByRole("button", { name: "Abrir proyecto Estudio Aurora", exact: true }).click();
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(officeRequests).toHaveLength(0);
  await page.getByRole("button", { name: "Abrir oficina 3D", exact: true }).click();
  const office = page.getByRole("dialog", { name: "Estudio Aurora", exact: true });
  await expect(office).toBeVisible();
  await expect(office.locator("canvas")).toHaveCount(1);
  await expect(office.locator(".office-world-label")).toHaveCount(6);
  await expect(office.locator(".office-member")).toHaveCount(6);
  await expect(office.getByText("Solo Boreal")).toHaveCount(0);
  await expect(office.locator(".office-scene-error")).toHaveCount(0);
  await expect(office.getByText("Actividad consultada al servidor")).toBeVisible();
  expect(officeRequests.length).toBeGreaterThan(0);
  await page.screenshot({ path: "../artifacts/office-desktop.png" });
  await office.getByRole("button", { name: "Vista superior", exact: true }).click();
  await expect(office.getByRole("button", { name: "Vista superior", exact: true })).toHaveAttribute("aria-pressed", "true");
  await office.getByRole("button", { name: "Acercar", exact: true }).click();
  await office.getByRole("button", { name: "Restablecer cámara", exact: true }).click();
  await office.locator(".office-world-label").filter({ hasText: "Nico" }).click();
  await expect(office.locator(".office-agent-detail h3")).toHaveText("Nico");
  const messages = page.waitForResponse(response => response.url().endsWith(`/api/agents/${coder.id}/messages`) && response.status() === 200);
  await office.getByRole("button", { name: "Abrir conversación" }).click();
  await messages;
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.locator("h1")).toContainText("Nico");
  expect(mutations).toHaveLength(0);
  expect(errors).toEqual([]);
});

test("each project opens its own office and Escape disposes it", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "Abrir oficina 3D de Proyecto Boreal", exact: true }).click();
  const office = page.getByRole("dialog", { name: "Proyecto Boreal", exact: true });
  await expect(office.locator(".office-member")).toHaveCount(2);
  await expect(office.locator(".office-world-label")).toHaveCount(2);
  await expect(office.getByText("Nico", { exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abrir oficina 3D de Proyecto Boreal", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Abrir oficina 3D de Estudio Aurora", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Estudio Aurora", exact: true }).locator(".office-member")).toHaveCount(6);
});

test("WebGL failure leaves an accessible team and functioning conversations", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type: string, ...args: unknown[]) {
      if (type.startsWith("webgl")) return null;
      return original.apply(this, [type, ...args] as Parameters<typeof original>);
    } as typeof original;
  });
  await setup(page);
  await page.getByRole("button", { name: "Abrir oficina 3D de Estudio Aurora", exact: true }).click();
  const office = page.getByRole("dialog", { name: "Estudio Aurora", exact: true });
  await expect(office.getByRole("alert")).toContainText("La vista 3D no está disponible");
  await office.locator(".office-member").filter({ hasText: "Nico" }).click();
  await office.getByRole("button", { name: "Abrir conversación" }).click();
  await expect(page.locator("h1")).toContainText("Nico");
});

test("the office and team remain usable on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.getByRole("button", { name: "Abrir oficina 3D de Estudio Aurora", exact: true }).click();
  const office = page.getByRole("dialog", { name: "Estudio Aurora", exact: true });
  await expect(office.locator("canvas")).toHaveCount(1);
  await expect(office.locator(".office-scene-error")).toHaveCount(0);
  await office.locator(".office-member").filter({ hasText: "Cata" }).click();
  await expect(office.getByRole("button", { name: "Abrir conversación" })).toBeVisible();
  expect(await office.evaluate(el => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  await page.screenshot({ path: "../artifacts/office-mobile.png" });
  await office.getByRole("button", { name: "Cerrar oficina 3D" }).click();
  await expect(page.locator("canvas")).toHaveCount(0);
});
