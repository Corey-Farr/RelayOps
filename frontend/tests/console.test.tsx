import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import type { ReactNode } from "react";
import { App } from "../src/App";
import {
  Events,
  EventDetail,
  IncidentDetail,
  EventSubmit,
} from "../src/pages/Operations";
import { Policies, Login } from "../src/pages/Controls";
import { ToastProvider } from "../src/components/ui";
import { api, setCsrf } from "../src/services/api";
function wrap(child: ReactNode, path = "/") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <ToastProvider>{child}</ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function mock(data: unknown, status = 200) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async () =>
        new Response(JSON.stringify(data), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
    );
}
const event = {
  id: "event-123",
  type: "order.created",
  created_at: "2026-01-01T00:00:00Z",
  status: "delivered",
  delivery_count: 1,
};
describe("authenticated console", () => {
  it("shows sign-in for an expired session", async () => {
    mock({ detail: "Not authenticated" }, 401);
    wrap(<App />);
    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toBeVisible();
  });
  it("renders navigation for a signed-in user and follows links", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input) =>
        new Response(
          JSON.stringify(
            String(input).includes("/auth/me")
              ? {
                  user: {
                    id: "1",
                    email: "viewer@example.com",
                    role: "viewer",
                  },
                  csrf_token: "token",
                }
              : [],
          ),
          { status: 200 },
        ),
    );
    wrap(<App />, "/events");
    expect(await screen.findByRole("navigation")).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: "Dead letters" }));
    expect(
      await screen.findByText(
        "No dead letters. Failed permanent deliveries will appear here.",
      ),
    ).toBeVisible();
  });
  it("displays API authentication errors", async () => {
    mock({ detail: "Invalid credentials" }, 401);
    wrap(<Login onLogin={() => {}} />);
    await userEvent.type(
      screen.getByLabelText("Email address"),
      "admin@example.com",
    );
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid credentials",
    );
  });
});
describe("events", () => {
  it("filters by query and status through the real API adapter", async () => {
    const fetch = mock([event]);
    wrap(<Events />);
    expect(await screen.findByText("order.created")).toBeVisible();
    await userEvent.type(screen.getByLabelText("Search events"), "order");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "delivered");
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([url]) =>
          String(url).includes("search=order&status=delivered"),
        ),
      ).toBe(true),
    );
  });
  it("renders an honest empty state", async () => {
    mock([]);
    wrap(<Events />);
    expect(
      await screen.findByText("No events match your filters."),
    ).toBeVisible();
  });
  it("renders API errors rather than fake metrics", async () => {
    mock({ detail: "Database unavailable" }, 503);
    wrap(<Events />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Database unavailable",
    );
  });
  it("provides a loading state while awaiting the backend", () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));
    wrap(<Events />);
    expect(screen.getByLabelText("Loading")).toBeVisible();
  });
  it("shows payload and real attempt details", async () => {
    mock({
      ...event,
      payload: { order_id: "order-42" },
      deliveries: [
        {
          id: "d1",
          destination_name: "Demo sink",
          status: "delivered",
          region: "us-east",
          policy_id: "p1",
          attempt_count: 1,
          attempts: [
            {
              id: "a1",
              number: 1,
              http_status: 200,
              duration_ms: 12.4,
              started_at: "2026-01-01T00:00:01Z",
              worker_id: "worker-1",
              region: "us-east",
              trace_id: "trace-abc",
            },
          ],
        },
      ],
    });
    wrap(
      <Routes>
        <Route path="/events/:id" element={<EventDetail />} />
      </Routes>,
      "/events/event-123",
    );
    expect(await screen.findByText("Attempt 1 · HTTP 200")).toBeVisible();
    expect(screen.getByText("trace-abc")).toBeVisible();
    expect(screen.getByText(/order-42/)).toBeVisible();
  });
  it("rejects invalid JSON before sending an event", async () => {
    const fetch = mock({});
    wrap(<EventSubmit projectId="p1" />);
    await userEvent.clear(screen.getByLabelText("JSON payload"));
    await userEvent.type(screen.getByLabelText("JSON payload"), "invalid");
    await userEvent.click(screen.getByRole("button", { name: "Submit event" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Payload must be valid JSON",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});
describe("operational controls", () => {
  it("acknowledges an incident with a CSRF-protected mutation", async () => {
    setCsrf("test-csrf");
    const incident = {
      id: "i1",
      title: "Delivery degradation",
      component: "sink",
      source: "monitor",
      status: "open",
      severity: "warning",
      description: "Retries exceeded threshold",
      evidence: { failed: 5 },
      timeline: [],
    };
    const fetch = mock(incident);
    wrap(
      <Routes>
        <Route path="/incidents/:id" element={<IncidentDetail />} />
      </Routes>,
      "/incidents/i1",
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Acknowledge incident" }),
    );
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "/api/incidents/i1/acknowledge",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf" }),
        }),
      ),
    );
  });
  it("requires confirmation before promoting candidate policy", async () => {
    const policy = {
      id: "p1",
      version: 1,
      timeout_seconds: 5,
      max_attempts: 5,
      backoff_base: 1,
      backoff_cap: 60,
    };
    const fetch = mock({
      stable: policy,
      candidate: { ...policy, id: "p2", version: 2 },
      canary_percent: 10,
      comparison: [],
      history: [],
    });
    wrap(<Policies />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Promote candidate" }),
    );
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(fetch.mock.calls.some(([, opts]) => opts?.method === "POST")).toBe(
      false,
    );
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url, opts]) =>
            String(url).endsWith("/policies/promote") &&
            opts?.method === "POST",
        ),
      ).toBe(true),
    );
  });
  it("rejects an inverted retry backoff range", async () => {
    mock({
      stable: null,
      candidate: null,
      canary_percent: 0,
      comparison: [],
      history: [],
    });
    wrap(<Policies />);
    const base = await screen.findByLabelText("Backoff base (seconds)");
    await userEvent.clear(base);
    await userEvent.type(base, "100");
    await userEvent.click(
      screen.getByRole("button", { name: "Publish candidate" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Backoff cap must be at least the base",
    );
  });
  it("sanitizes structured server validation into a readable error", async () => {
    mock({ detail: [{ msg: "Field required" }] }, 422);
    await expect(api("/events", "POST", {})).rejects.toThrow("Field required");
  });
});
