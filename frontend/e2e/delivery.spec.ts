import { test, expect } from "@playwright/test";

test("login, select demo project, deliver, fail and recover a real webhook", async ({
  page,
}) => {
  if (!process.env.ADMIN_EMAIL || !process.env.ADMIN_PASSWORD)
    throw new Error("Set ADMIN_EMAIL and ADMIN_PASSWORD from local setup");
  await page.goto("/");
  await page.getByLabel("Email address").fill(process.env.ADMIN_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Delivery overview" }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/auth/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  await page.request.post("/api/lab/scenario", {
    headers,
    data: { mode: "normal" },
  });
  try {
    await page.getByRole("link", { name: "Settings", exact: true }).click();
    await page
      .getByLabel("Active project")
      .selectOption({ label: "Demo project" });
    await expect(
      page.getByRole("heading", { name: "Demo receiver", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Edit destination", exact: true })
      .click();
    await expect(
      page.getByLabel("Event subscriptions", { exact: true }),
    ).toHaveValue("*");
    const saved = page.waitForResponse(
      (response) =>
        response.url().includes("/api/destinations/") &&
        response.request().method() === "PATCH",
    );
    await page
      .getByRole("button", { name: "Save destination", exact: true })
      .click();
    expect((await saved).status()).toBe(200);
    await expect(
      page.getByRole("button", { name: "Edit destination", exact: true }),
    ).toBeVisible();
    await page.getByLabel("Event type", { exact: true }).fill("e2e.normal");
    await page
      .getByLabel("JSON payload")
      .fill(JSON.stringify({ source: "playwright", run: Date.now() }));
    await page
      .getByRole("button", { name: "Submit event", exact: true })
      .click();
    await page
      .getByRole("link", { name: "View delivery", exact: true })
      .click();
    await expect(page.getByText("Attempt 1 · HTTP 200")).toBeVisible({
      timeout: 30_000,
    });
    const normalId = page.url().split("/").pop();
    const normal = await (
      await page.request.get(`/api/events/${normalId}`)
    ).json();
    expect(normal.status).toBe("delivered");
    expect(normal.deliveries[0].attempts[0].http_status).toBe(200);
    if (process.env.CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../docs/screenshots/event-delivery.png",
        fullPage: true,
      });

    await page
      .getByRole("link", { name: "Reliability lab", exact: true })
      .click();
    await page.getByRole("button", { name: /Destination outage/ }).click();
    await expect
      .poll(
        async () => (await (await page.request.get("/api/lab")).json()).mode,
      )
      .toBe("unavailable");
    const projectId = normal.project_id;
    const accepted = await page.request.post("/api/events", {
      headers: { ...headers, "Idempotency-Key": `e2e-fault-${Date.now()}` },
      data: {
        project_id: projectId,
        type: "e2e.recovery",
        payload: { source: "playwright" },
      },
    });
    expect(accepted.status()).toBe(201);
    const fault = await accepted.json();
    await expect
      .poll(
        async () => {
          const event = await (
            await page.request.get(`/api/events/${fault.id}`)
          ).json();
          return event.deliveries.some(
            (d: { attempts: { http_status: number }[] }) =>
              d.attempts.some((a) => a.http_status === 503),
          );
        },
        { timeout: 30_000 },
      )
      .toBe(true);
    await page.getByRole("button", { name: /Normal operation/ }).click();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/events/${fault.id}`)).json())
            .status,
        { timeout: 60_000 },
      )
      .toBe("delivered");
    await page.goto(`/events/${fault.id}`);
    await expect(page.getByText(/HTTP 503/).first()).toBeVisible();
    await expect(page.getByText(/HTTP 200/).first()).toBeVisible();
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await expect(page.locator(".recharts-surface").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Delivery overview" }),
    ).toBeVisible();
    // A native confirmation dialog must contain keyboard focus without changing state.
    await page.getByRole("link", { name: "Worker pools", exact: true }).click();
    const pause = page
      .getByRole("button", { name: "Pause pool", exact: true })
      .first();
    await pause.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(
      dialog.getByRole("button", { name: "Confirm", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(pause).toBeFocused();
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await expect(page.locator(".recharts-surface").first()).toBeVisible();
    if (process.env.CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../docs/screenshots/overview.png",
        fullPage: true,
      });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    await page
      .getByRole("link", { name: "Event explorer", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Event explorer" }),
    ).toBeVisible();
    await expect
      .poll(async () =>
        page
          .locator(".sidebar")
          .evaluate((el) => el.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    if (process.env.CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../docs/screenshots/mobile-events.png",
        fullPage: true,
      });
  } finally {
    await page.request.post("/api/lab/scenario", {
      headers,
      data: { mode: "normal" },
    });
  }
});
