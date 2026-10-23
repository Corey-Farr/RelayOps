import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, percent, stamp } from "../services/api";
import {
  Empty,
  Failure,
  Loading,
  PageTitle,
  Status,
  Json,
  useAction,
  ConfirmButton,
} from "../components/ui";
import { useData, Workers, EventSubmit } from "./Operations";
const scenarios = [
  ["normal", "Normal operation", "Successful acknowledgements"],
  ["intermittent", "Intermittent errors", "Deterministic HTTP 500 failures"],
  ["rate_limit", "Rate limiting", "HTTP 429 with retry guidance"],
  ["latency", "High latency", "Delayed real HTTP responses"],
  ["timeout", "Request timeouts", "Responses exceed delivery deadlines"],
  ["unavailable", "Destination outage", "All requests fail with HTTP 503"],
];
export function Lab() {
  const q = useData("/lab");
  const projects = useData("/projects");
  const [project, setProject] = useState("");
  const [count, setCount] = useState(10);
  const scenario = useAction("/lab/scenario");
  const generate = useAction("/lab/generate");
  const selected = project || projects.data?.[0]?.id || "";
  return (
    <>
      <PageTitle
        eyebrow="CONTROLLED EXPERIMENTS"
        title="Reliability lab"
        description="Exercise real failures. Observe retries. Prove recovery."
      />
      <div className="safety-note">
        <strong>Local demonstration environment</strong>
        <span>
          Faults affect only the configured demo receiver. Worker controls
          affect logical local pools.
        </span>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : !q.data.enabled ? (
        <Empty>The reliability lab is disabled by server configuration.</Empty>
      ) : (
        <>
          <section className="panel">
            <div className="panel-title">
              <div>
                <h2>Destination behavior</h2>
                <p>
                  Each scenario changes actual HTTP responses from the demo
                  sink.
                </p>
              </div>
              <Status value={q.data.mode} />
            </div>
            <div className="scenario-grid">
              {scenarios.map(([mode, title, description]) => (
                <button
                  key={mode}
                  className={`scenario ${q.data.mode === mode ? "selected" : ""}`}
                  disabled={scenario.isPending}
                  onClick={() => scenario.mutate({ mode })}
                >
                  <span className="scenario-indicator" />
                  <strong>{title}</strong>
                  <small>{description}</small>
                </button>
              ))}
            </div>
            <div className="actions">
              <ConfirmButton
                disabled={scenario.isPending || q.data.mode === "normal"}
                onConfirm={() => scenario.mutate({ mode: "normal" })}
              >
                Stop faults / reset behavior
              </ConfirmButton>
              <span className="note">
                Reset preserves exercise history and accepted events.
              </span>
            </div>
          </section>
          <section className="panel">
            <h2>Generate controlled traffic</h2>
            <p>
              Seed 42 produces reproducible payloads. A burst is limited to 100
              real events.
            </p>
            <form
              className="inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                generate.mutate({ project_id: selected, count, seed: 42 });
              }}
            >
              <label>
                Project
                <select
                  required
                  value={selected}
                  onChange={(e) => setProject(e.target.value)}
                >
                  <option value="" disabled>
                    Select project
                  </option>
                  {projects.data?.map((p: any) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Events per burst
                <input
                  type="number"
                  min="1"
                  max="100"
                  required
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
              </label>
              <button
                className="primary"
                disabled={generate.isPending || !selected}
              >
                {generate.isPending ? "Generating…" : "Generate events"}
              </button>
            </form>
            {generate.data && (
              <p role="status">
                Accepted {generate.data.accepted} events. Follow delivery in the
                event explorer.
              </p>
            )}
          </section>
          <Workers compact />
          <section className="panel">
            <h2>Exercise history</h2>
            {q.data.history.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Behavior</th>
                      <th>Events</th>
                      <th>Actor</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.history.map((h: any) => (
                      <tr key={h.id}>
                        <td>
                          <Status value={h.mode} />
                        </td>
                        <td>{h.event_count ?? "—"}</td>
                        <td>{h.actor}</td>
                        <td>{stamp(h.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty>No exercises have been run.</Empty>
            )}
          </section>
        </>
      )}
    </>
  );
}
export function Policies() {
  const q = useData("/policies");
  const create = useAction("/policies/candidate");
  const promote = useAction("/policies/promote");
  const rollback = useAction("/policies/rollback");
  const [values, setValues] = useState({
    timeout_seconds: 5,
    max_attempts: 5,
    backoff_base: 1,
    backoff_cap: 60,
    canary_percent: 10,
  });
  const [error, setError] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    if (values.backoff_cap < values.backoff_base) {
      setError("Backoff cap must be at least the base.");
      return;
    }
    setError("");
    create.mutate(values);
  }
  return (
    <>
      <PageTitle
        title="Release policies"
        description="Roll out versioned delivery settings with deterministic canary assignment. These releases do not deploy application binaries."
      />
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : (
        <>
          <div className="two-grid">
            {[
              ["Stable policy", q.data.stable],
              ["Candidate policy", q.data.candidate],
            ].map(([title, p]: any) => (
              <section className="panel" key={title}>
                <div className="panel-title">
                  <h2>{title}</h2>
                  {p && <span className="tag">v{p.version}</span>}
                </div>
                {p ? (
                  <dl>
                    {[
                      "timeout_seconds",
                      "max_attempts",
                      "backoff_base",
                      "backoff_cap",
                    ].map((k) => (
                      <div key={k}>
                        <dt>{k.replaceAll("_", " ")}</dt>
                        <dd>
                          {p[k]}
                          {k !== "max_attempts" ? " s" : ""}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <Empty>
                    No candidate. Publish a policy to start a canary.
                  </Empty>
                )}
              </section>
            ))}
          </div>
          <section className="panel">
            <div className="panel-title">
              <div>
                <h2>Canary rollout</h2>
                <p>
                  {q.data.canary_percent}% of newly created deliveries assigned
                  to the candidate.
                </p>
              </div>
              <div className="actions">
                <ConfirmButton
                  disabled={!q.data.candidate || promote.isPending}
                  onConfirm={() => promote.mutate(undefined)}
                >
                  Promote candidate
                </ConfirmButton>
                <ConfirmButton
                  disabled={!q.data.candidate || rollback.isPending}
                  onConfirm={() => rollback.mutate(undefined)}
                >
                  Roll back candidate
                </ConfirmButton>
              </div>
            </div>
            <p className="note">
              Existing deliveries retain their selected policy through retries.
            </p>
            <form className="form-grid" onSubmit={submit}>
              {Object.entries(values).map(([key, value]) => (
                <label key={key}>
                  {
                    (
                      {
                        timeout_seconds: "HTTP timeout (seconds)",
                        max_attempts: "Maximum attempts",
                        backoff_base: "Backoff base (seconds)",
                        backoff_cap: "Backoff cap (seconds)",
                        canary_percent: "Canary traffic (%)",
                      } as Record<string, string>
                    )[key]
                  }
                  <input
                    required
                    type="number"
                    min={
                      key === "canary_percent"
                        ? 0
                        : key === "max_attempts"
                          ? 1
                          : 0.1
                    }
                    max={
                      key === "canary_percent"
                        ? 100
                        : key === "max_attempts"
                          ? 20
                          : 300
                    }
                    step={
                      key === "max_attempts" || key === "canary_percent"
                        ? 1
                        : 0.1
                    }
                    value={value}
                    onChange={(e) =>
                      setValues({ ...values, [key]: Number(e.target.value) })
                    }
                  />
                </label>
              ))}
              <div className="form-action">
                <button className="primary" disabled={create.isPending}>
                  Publish candidate
                </button>
              </div>
              {error && (
                <p role="alert" className="error-text">
                  {error}
                </p>
              )}
            </form>
          </section>
          <section className="panel">
            <h2>Measured policy outcomes</h2>
            {q.data.comparison.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Policy ID</th>
                      <th>Deliveries</th>
                      <th>Delivered</th>
                      <th>Dead letters</th>
                      <th>Success</th>
                      <th>p95 latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.comparison.map((c: any) => (
                      <tr key={c.policy_id}>
                        <td className="mono">{c.policy_id.slice(0, 12)}</td>
                        <td>{c.total}</td>
                        <td>{c.delivered}</td>
                        <td>{c.dead_letter}</td>
                        <td>{percent(c.success_rate)}</td>
                        <td>
                          {c.p95_latency_ms == null
                            ? "Insufficient data"
                            : `${Math.round(c.p95_latency_ms)} ms`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty>Measured results appear after deliveries complete.</Empty>
            )}
          </section>
          <section className="panel">
            <h2>Release history</h2>
            {q.data.history.length ? (
              <div className="history">
                {q.data.history.map((h: any, n: number) => (
                  <div key={h.id ?? n} className="list-item">
                    <div>
                      <strong>{h.action}</strong>
                      <p>
                        {h.actor} · {stamp(h.created_at)}
                      </p>
                    </div>
                    <Json value={h.details} />
                  </div>
                ))}
              </div>
            ) : (
              <Empty>No policy changes yet.</Empty>
            )}
          </section>
        </>
      )}
    </>
  );
}
export function Settings() {
  const projects = useData("/projects");
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const add = useAction("/projects");
  const project = selected || projects.data?.[0]?.id || "";
  return (
    <>
      <PageTitle
        title="Project settings"
        description="Manage destinations, project access, and authenticated event ingestion."
      />
      <section className="panel">
        <h2>Projects</h2>
        {projects.isPending ? (
          <Loading />
        ) : projects.error ? (
          <Failure error={projects.error} />
        ) : (
          <div className="inline-form">
            <label>
              Active project
              <select
                value={project}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="" disabled>
                  Select project
                </option>
                {projects.data.map((p: any) => (
                  <option value={p.id} key={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <form
              className="inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                add.mutate(
                  { name },
                  {
                    onSuccess: (p: any) => {
                      setName("");
                      setSelected(p.id);
                    },
                  },
                );
              }}
            >
              <label>
                New project name
                <input
                  required
                  minLength={2}
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My application"
                />
              </label>
              <button disabled={add.isPending} className="primary">
                Create project
              </button>
            </form>
          </div>
        )}
      </section>
      {project ? (
        <>
          <Destinations projectId={project} />
          <div className="two-grid">
            <section className="panel">
              <Keys projectId={project} />
            </section>
            <section className="panel">
              <EventSubmit projectId={project} />
            </section>
          </div>
        </>
      ) : (
        <Empty>Create a project to configure destinations and API keys.</Empty>
      )}
      <section className="panel">
        <h2>Authentication & access</h2>
        <p>
          Sessions use HttpOnly cookies and CSRF protection. Ingestion keys are
          scoped to one project and revealed only once. User roles and account
          bootstrap are managed by the server administrator.
        </p>
        <p className="note">
          Roles: admin manages projects and keys; operator controls delivery
          operations; viewer has read access. Server-side authorization applies
          to every action.
        </p>
      </section>
      <Audit />
    </>
  );
}
function Destinations({ projectId }: { projectId: string }) {
  const q = useData(`/destinations?project_id=${projectId}`);
  const add = useAction("/destinations");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("http://demo-sink:8081/webhook");
  const [types, setTypes] = useState("*");
  const [secret, setSecret] = useState("");
  return (
    <section className="panel">
      <h2>HTTP destinations</h2>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : q.data.length ? (
        q.data.map((d: any) => <Destination key={d.id} d={d} />)
      ) : (
        <Empty>No destinations for this project.</Empty>
      )}
      <form
        className="form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(
            {
              project_id: projectId,
              name,
              url,
              event_types: types
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean),
            },
            {
              onSuccess: (d: any) => {
                setSecret(d.signing_secret || "");
                setName("");
              },
            },
          );
        }}
      >
        <label>
          Destination name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Order receiver"
          />
        </label>
        <label>
          Destination URL
          <input
            required
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <label>
          Event types (comma separated)
          <input
            required
            value={types}
            onChange={(e) => setTypes(e.target.value)}
          />
        </label>
        <div className="form-action">
          <button className="primary" disabled={add.isPending}>
            Add destination
          </button>
        </div>
      </form>
      {secret && (
        <div className="secret" role="status">
          <strong>Signing secret — shown once</strong>
          <code>{secret}</code>
          <button onClick={() => setSecret("")}>Dismiss secret</button>
        </div>
      )}
      <p className="note">
        Production requires approved HTTPS hosts. Local demo HTTP is limited to
        the configured demo sink.
      </p>
    </section>
  );
}
function Destination({ d }: { d: any }) {
  const toggle = useAction(`/destinations/${d.id}`, "PATCH");
  return (
    <div className="list-item">
      <div>
        <h3>{d.name}</h3>
        <p>{d.url}</p>
        <small>Subscriptions: {d.event_types.join(", ")}</small>
      </div>
      <div className="actions">
        <Status value={d.enabled ? "enabled" : "disabled"} />
        <ConfirmButton
          disabled={toggle.isPending}
          onConfirm={() => toggle.mutate({ enabled: !d.enabled })}
        >
          {d.enabled ? "Disable destination" : "Enable destination"}
        </ConfirmButton>
      </div>
    </div>
  );
}
function Keys({ projectId }: { projectId: string }) {
  const q = useData(`/projects/${projectId}/keys`);
  const create = useAction(`/projects/${projectId}/keys`);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  return (
    <>
      <h2>Ingestion API keys</h2>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : q.data.length ? (
        q.data.map((k: any) => <KeyRow key={k.id} item={k} />)
      ) : (
        <Empty>No API keys created.</Empty>
      )}
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(
            { name },
            {
              onSuccess: (r: any) => {
                setKey(r.key);
                setName("");
              },
            },
          );
        }}
      >
        <label>
          Key name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Development client"
          />
        </label>
        <button disabled={create.isPending}>Create API key</button>
      </form>
      {key && (
        <div className="secret" role="status">
          <strong>Copy this key now. It will not be shown again.</strong>
          <code>{key}</code>
          <button onClick={() => setKey("")}>Dismiss key</button>
        </div>
      )}
      <p className="note">
        To rotate: create a replacement, update your client, then revoke the old
        key.
      </p>
    </>
  );
}
function KeyRow({ item: k }: { item: any }) {
  const revoke = useAction(`/keys/${k.id}`, "DELETE");
  return (
    <div className="list-item">
      <div>
        <strong>{k.name}</strong>
        <p className="mono">{k.prefix}…</p>
      </div>
      {k.revoked_at ? (
        <Status value="revoked" />
      ) : (
        <ConfirmButton
          disabled={revoke.isPending}
          onConfirm={() => revoke.mutate(undefined)}
        >
          Revoke key
        </ConfirmButton>
      )}
    </div>
  );
}
function Audit() {
  const q = useData("/audit?limit=100");
  return (
    <section className="panel">
      <h2>Administrative audit trail</h2>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : q.data.length ? (
        <div className="table-wrap audit">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Actor</th>
                <th>Resource</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((a: any) => (
                <tr key={a.id}>
                  <td>{a.action}</td>
                  <td>{a.actor}</td>
                  <td>{a.resource}</td>
                  <td>{stamp(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>No administrative actions recorded.</Empty>
      )}
    </section>
  );
}
export function Login({ onLogin }: { onLogin: () => void }) {
  const client = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", "POST", { email, password });
      await client.invalidateQueries({ queryKey: ["session"] });
      onLogin();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <div className="login-brand">
        <div className="brand-icon">R</div>
        <span>RelayOps</span>
      </div>
      <div className="login-card">
        <div className="eyebrow">RELIABILITY STARTS HERE</div>
        <h1>Welcome back.</h1>
        <p>Sign in to your event delivery control plane.</p>
        <form className="form" onSubmit={submit}>
          <label>
            Email address
            <input
              autoComplete="username"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="note">
          Use the administrator credentials generated during local setup.
        </p>
      </div>
      <p className="login-footer">
        Durable events. Observable delivery. Controlled recovery.
      </p>
    </main>
  );
}
