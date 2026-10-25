import { ActionForm, usePermissions } from "../components/access";
import { useState, useEffect, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  ArrowUpRight,
  Activity,
  Clock,
  Layers,
  CheckCircle2,
} from "lucide-react";
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
export function useData(path: string) {
  return useQuery({
    queryKey: [path],
    queryFn: () => api(path),
    refetchInterval: 5000,
  });
}
export function Overview() {
  const q = useData("/overview");
  if (q.isPending) return <Loading />;
  if (q.error)
    return <Failure error={q.error} retry={() => void q.refetch()} />;
  const d = q.data;
  return (
    <>
      <PageTitle
        eyebrow="LIVE CONTROL PLANE"
        title="Delivery overview"
        description="A clear view of every event, every destination, and every recovery."
      >
        <Link className="button primary" to="/lab">
          Generate traffic <ArrowUpRight size={16} />
        </Link>
      </PageTitle>
      <div className="metric-grid">
        {[
          [
            Layers,
            "Queue depth",
            d.queue_depth,
            "Pending and retrying deliveries",
          ],
          [
            CheckCircle2,
            "Delivery success",
            percent(d.success_rate),
            "All recorded delivery outcomes",
          ],
          [
            Clock,
            "p95 delivery latency",
            d.p95_latency_ms == null
              ? "No samples"
              : `${Math.round(d.p95_latency_ms)} ms`,
            "Measured end-to-end latency",
          ],
          [
            Activity,
            "Throughput",
            `${d.throughput_per_minute ?? 0}/min`,
            "Observed delivery completions",
          ],
        ].map(([Icon, label, value, sub]: any) => (
          <article className="metric" key={label}>
            <div className="metric-label">
              {label}
              <Icon size={18} />
            </div>
            <strong>{value}</strong>
            <small>{sub}</small>
          </article>
        ))}
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-title">
            <div>
              <h2>Event traffic</h2>
              <p>Accepted and delivered · Last 24 hours</p>
            </div>
            <span className="live-dot">Live</span>
          </div>
          {d.series?.some((v: any) => v.accepted || v.delivered || v.failed) ? (
            <div className="chart">
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={d.series}>
                  <defs>
                    <linearGradient id="traffic" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor="#10a88c"
                        stopOpacity={0.25}
                      />
                      <stop offset="100%" stopColor="#10a88c" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                    stroke="#e7edf2"
                  />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(s) =>
                      new Date(s).toLocaleTimeString([], { hour: "2-digit" })
                    }
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(s) => stamp(String(s))} />
                  <Area
                    isAnimationActive={false}
                    type="monotone"
                    dataKey="accepted"
                    stroke="#7583cb"
                    fill="transparent"
                    strokeWidth={2}
                  />
                  <Area
                    isAnimationActive={false}
                    type="monotone"
                    dataKey="delivered"
                    stroke="#10a88c"
                    fill="url(#traffic)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty>
              No traffic in this observation window. Generate demo events to see
              measured activity.
            </Empty>
          )}
          <div className="legend">
            <span className="green-dot" /> Delivered{" "}
            <span className="purple-dot" /> Accepted
          </div>
        </section>
        <section className="panel slo">
          <div className="panel-title">
            <h2>Reliability objective</h2>
            <span className="tag">{d.slo.window_hours}h window</span>
          </div>
          <div className="slo-value">{percent(d.slo.compliance)}</div>
          <p>
            Target {percent(d.slo.target)} within {d.slo.deadline_seconds}{" "}
            seconds
          </p>
          <div className="progress">
            <span style={{ width: `${(d.slo.compliance ?? 0) * 100}%` }} />
          </div>
          <dl>
            <div>
              <dt>Matured deliveries</dt>
              <dd>{d.slo.eligible}</dd>
            </div>
            <div>
              <dt>Error budget remaining</dt>
              <dd>{percent(d.slo.error_budget_remaining)}</dd>
            </div>
            <div>
              <dt>Burn rate</dt>
              <dd>
                {d.slo.sufficient_data
                  ? `${d.slo.burn_rate?.toFixed(2) ?? "—"}×`
                  : "Insufficient samples"}
              </dd>
            </div>
          </dl>
          <p className="note">
            Only deliveries with a completed observation window count toward
            this objective.
            {!d.slo.sufficient_data &&
              " Insufficient samples to assess reliability; displayed percentages are preliminary."}
          </p>
        </section>
      </div>
      <div className="three-grid">
        {[
          ["In flight", d.in_flight, "Actively leased jobs"],
          ["Dead letters", d.dead_letter, "Deliveries requiring review"],
          [
            "Estimated queue drain",
            d.estimated_drain_seconds == null
              ? "Insufficient data"
              : `${Math.ceil(d.estimated_drain_seconds)} sec`,
            "Based on observed processing rate",
          ],
        ].map(([label, value, sub]) => (
          <section className="panel mini" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{sub}</small>
          </section>
        ))}
      </div>
      <Workers compact />
      <div className="three-grid">
        <section className="panel mini">
          <span>Events accepted</span>
          <strong>{d.events_total}</strong>
        </section>
        <section className="panel mini">
          <span>Active incidents</span>
          <strong>{d.active_incidents ?? "—"}</strong>
          <Link to="/incidents">Inspect incidents</Link>
        </section>
        <section className="panel mini">
          <span>p99 delivery latency</span>
          <strong>
            {d.p99_latency_ms == null
              ? "No samples"
              : `${Math.round(d.p99_latency_ms)} ms`}
          </strong>
          <small>Acceptance to successful delivery</small>
        </section>
      </div>
      <section className="panel">
        <h2>Recent events</h2>
        {d.recent_events?.length ? (
          d.recent_events.map((e: any) => (
            <div className="list-item" key={e.id}>
              <Link to={`/events/${e.id}`}>
                {e.type} · {e.id.slice(0, 12)}
              </Link>
              <Status value={e.status} />
              <span>{stamp(e.created_at)}</span>
            </div>
          ))
        ) : (
          <Empty>No accepted events yet.</Empty>
        )}
      </section>
    </>
  );
}
export function Workers({ compact = false }: { compact?: boolean }) {
  const q = useData("/workers");
  return (
    <>
      {!compact && (
        <PageTitle
          title="Worker pools"
          description="Independent processing pools in three logical regions. Local simulation, not geographic redundancy."
        />
      )}
      <section className="panel">
        <div className="panel-title">
          <div>
            <h2>Logical regions</h2>
            <p>Persisted heartbeats and safe pool controls</p>
          </div>
          <span className="tag">LOCAL TOPOLOGY</span>
        </div>
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : (
          <div className="three-grid">
            {q.data.pools.map((p: any) => (
              <Pool key={p.region} pool={p} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
function Pool({ pool: p }: { pool: any }) {
  const pause = useAction(
    `/workers/${p.region}/${p.paused ? "resume" : "pause"}`,
  );
  return (
    <article className="pool">
      <div className="row">
        <h3>{p.region}</h3>
        <Status
          value={p.paused ? "paused" : p.healthy ? "healthy" : "unavailable"}
        />
      </div>
      <p>
        {p.workers.length} registered worker{p.workers.length === 1 ? "" : "s"}
      </p>
      <p>
        {p.active_worker_count ?? "—"} active · {p.assigned_queue_depth ?? "—"}{" "}
        assigned queued
      </p>
      <p>
        {p.attempts_last_30m ?? "—"} attempts ·{" "}
        {p.failover_attempts_last_30m ?? "—"} failover attempts (30m)
      </p>
      {p.workers.map((w: any) => (
        <div className="worker" key={w.id}>
          <code>{w.id}</code>
          <small>
            Capacity {w.capacity} · {w.state} · v{w.version}
          </small>
          <small>Heartbeat {stamp(w.last_heartbeat)}</small>
        </div>
      ))}
      <ConfirmButton
        disabled={pause.isPending}
        onConfirm={() => pause.mutate(undefined)}
      >
        {p.paused ? "Resume pool" : "Pause pool"}
      </ConfirmButton>
    </article>
  );
}
export function Events() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState({
    project_id: "",
    destination_id: "",
    event_type: "",
    created_from: "",
    created_to: "",
    sort: "created_at",
    direction: "desc",
  });
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value)
      params.set(
        key,
        key.startsWith("created_") ? new Date(value).toISOString() : value,
      );
  });
  const q = useData(
    `/events?limit=11&offset=${page * 10}&search=${encodeURIComponent(search)}&status=${status}&${params}`,
  );
  useEffect(() => {
    if (q.isSuccess && q.data.length === 0 && page > 0) setPage(page - 1);
  }, [q.isSuccess, q.data, page]);
  return (
    <>
      <PageTitle
        title="Event explorer"
        description="Follow accepted events through each destination and delivery attempt."
      />
      <section className="panel">
        <div className="filters">
          <label className="search">
            Search events
            <input
              aria-label="Search events"
              placeholder="Event ID or type…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All statuses</option>
              {[
                "pending",
                "processing",
                "delivered",
                "partial_failure",
                "dead_letter",
                "retry_wait",
                "leased",
                "no_destinations",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          {(
            [
              ["event_type", "Event type filter"],
              ["project_id", "Project ID filter"],
              ["destination_id", "Destination ID filter"],
              ["created_from", "Accepted from"],
              ["created_to", "Accepted until"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type={key.startsWith("created_") ? "datetime-local" : "text"}
                value={filters[key]}
                onChange={(e) => {
                  setFilters({ ...filters, [key]: e.target.value });
                  setPage(0);
                }}
              />
            </label>
          ))}
          <label>
            Sort by
            <select
              value={filters.sort}
              onChange={(e) => {
                setFilters({ ...filters, sort: e.target.value });
                setPage(0);
              }}
            >
              <option value="created_at">Accepted time</option>
              <option value="type">Event type</option>
              <option value="id">Event ID</option>
            </select>
          </label>
          <label>
            Sort direction
            <select
              value={filters.direction}
              onChange={(e) => {
                setFilters({ ...filters, direction: e.target.value });
                setPage(0);
              }}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </div>
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : !q.data.length ? (
          <Empty>No events match your filters.</Empty>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Destinations</th>
                    <th>Accepted</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {q.data.slice(0, 10).map((e: any) => (
                    <tr key={e.id}>
                      <td>
                        <Link className="mono" to={`/events/${e.id}`}>
                          {e.id.slice(0, 12)}…
                        </Link>
                      </td>
                      <td>{e.type}</td>
                      <td>
                        <Status value={e.status} />
                      </td>
                      <td>{e.delivery_count}</td>
                      <td>{stamp(e.created_at)}</td>
                      <td>
                        <Link
                          aria-label={`View event ${e.id}`}
                          to={`/events/${e.id}`}
                        >
                          <ArrowUpRight size={16} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination" aria-label="Event pages">
              <button disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous page
              </button>
              <span>Page {page + 1}</span>
              <button
                disabled={q.data.length <= 10}
                onClick={() => setPage(page + 1)}
              >
                Next page
              </button>
            </div>
          </>
        )}
      </section>
    </>
  );
}
export function EventDetail() {
  const { id } = useParams();
  const q = useData(`/events/${id}`);
  if (q.isPending) return <Loading />;
  if (q.error) return <Failure error={q.error} />;
  const e = q.data;
  return (
    <>
      <Link className="back" to="/events">
        ← Event explorer
      </Link>
      <PageTitle title={e.type} description={`Event ${e.id}`}>
        <Status value={e.status} />
      </PageTitle>
      <section className="panel">
        <h2>Event payload</h2>
        <p>Accepted {stamp(e.created_at)}</p>
        <Json value={e.payload} />
      </section>
      <h2 className="section-title">Destination delivery history</h2>
      {e.deliveries.length ? (
        e.deliveries.map((d: any) => <Delivery key={d.id} delivery={d} />)
      ) : (
        <Empty>
          No matching destinations were subscribed when this event was accepted.
        </Empty>
      )}
    </>
  );
}
function Delivery({ delivery: d }: { delivery: any }) {
  const redrive = useAction(`/deliveries/${d.id}/redrive`);
  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>{d.destination_name}</h2>
          <p>
            {d.region} · Policy {d.policy_id} · {d.attempt_count} attempts
          </p>
        </div>
        <Status value={d.status} />
      </div>
      {d.status === "dead_letter" && (
        <ConfirmButton
          disabled={redrive.isPending}
          onConfirm={() => redrive.mutate(undefined)}
        >
          Redrive delivery
        </ConfirmButton>
      )}
      {d.next_attempt_at && <p>Next attempt {stamp(d.next_attempt_at)}</p>}
      {d.dispatches
        ?.filter((s: any) => !s.outcome_recorded)
        .map((s: any) => (
          <div className="safety-note" key={s.id}>
            <strong>Dispatch {s.number}: outcome unknown</strong>
            <span>
              Dispatch intent persisted {stamp(s.started_at)} by {s.worker_id}.
              No completion was recorded. The receiver may have accepted it; a
              recovered attempt can duplicate delivery.
            </span>
          </div>
        ))}
      {d.attempts.length ? (
        <ol className="timeline">
          {d.attempts.map((a: any) => (
            <li key={a.id}>
              <div className="row">
                <strong>
                  Attempt {a.number} ·{" "}
                  {a.http_status
                    ? `HTTP ${a.http_status}`
                    : a.failure_category || "Completed"}
                </strong>
                <span>{a.duration_ms?.toFixed(1)} ms</span>
              </div>
              <p>
                {stamp(a.started_at)} · {a.region} · {a.worker_id}
              </p>
              {a.error && <p className="error-text">{a.error}</p>}
              {a.trace_id && (
                <small>
                  Trace <code>{a.trace_id}</code>
                </small>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <Empty>No dispatch attempts yet.</Empty>
      )}
    </section>
  );
}
export function DeadLetters() {
  const q = useData("/deliveries?status=dead_letter");
  return (
    <>
      <PageTitle
        title="Dead letters"
        description="Inspect failed deliveries before safely requesting another delivery cycle."
      />
      <section className="panel">
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : q.data.length ? (
          q.data.map((d: any) => (
            <div key={d.id} className="list-item">
              <div>
                <h3>{d.type}</h3>
                <p>
                  {d.destination_name} · {d.attempt_count} attempts
                </p>
              </div>
              <Link className="button" to={`/events/${d.event_id}`}>
                Inspect & redrive
              </Link>
            </div>
          ))
        ) : (
          <Empty>
            No dead letters. Failed permanent deliveries will appear here.
          </Empty>
        )}
      </section>
    </>
  );
}
export function Incidents() {
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [page, setPage] = useState(0);
  const q = useData(
    `/incidents?limit=11&offset=${page * 10}&status=${status}&severity=${severity}`,
  );
  const rows = q.data ?? [];
  useEffect(() => {
    if (q.isSuccess && q.data.length === 0 && page > 0) setPage(page - 1);
  }, [q.isSuccess, q.data, page]);
  return (
    <>
      <PageTitle
        title="Incidents"
        description="Investigate reliability signals, acknowledge ownership, and document recovery."
      />
      <section className="panel">
        <div className="filters">
          <label>
            Status
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All statuses</option>
              {["open", "acknowledged", "resolved"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Severity
            <select
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All severities</option>
              {["critical", "warning", "info"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : rows.length ? (
          <>
            {rows.slice(0, 10).map((i: any) => (
              <Link
                className="incident list-item"
                key={i.id}
                to={`/incidents/${i.id}`}
              >
                <div>
                  <div className="row">
                    <Status value={i.severity} />
                    <h3>{i.title}</h3>
                  </div>
                  <p>
                    {i.component} · {stamp(i.created_at)}
                  </p>
                </div>
                <Status value={i.status} />
              </Link>
            ))}
            <div className="pagination" aria-label="Incident pages">
              <button disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous page
              </button>
              <span>Page {page + 1}</span>
              <button
                disabled={rows.length <= 10}
                onClick={() => setPage(page + 1)}
              >
                Next page
              </button>
            </div>
          </>
        ) : (
          <Empty>No incidents match these filters.</Empty>
        )}
      </section>
    </>
  );
}
export function IncidentDetail() {
  const { canOperate } = usePermissions();
  const { id } = useParams();
  const q = useData(`/incidents/${id}`);
  const ack = useAction(`/incidents/${id}/acknowledge`);
  const resolve = useAction(`/incidents/${id}/resolve`);
  if (q.isPending) return <Loading />;
  if (q.error) return <Failure error={q.error} />;
  const i = q.data;
  return (
    <>
      <Link className="back" to="/incidents">
        ← Incidents
      </Link>
      <PageTitle title={i.title} description={`${i.component} · ${i.source}`}>
        <Status value={i.status} />
      </PageTitle>
      <section className="panel">
        <div className="row">
          <Status value={i.severity} />
          <span>Opened {stamp(i.created_at)}</span>
        </div>
        <p>{i.description}</p>
        <div className="actions">
          {i.status === "open" && (
            <button
              className="primary"
              disabled={ack.isPending || !canOperate}
              onClick={() => ack.mutate(undefined)}
            >
              Acknowledge incident
            </button>
          )}
          {i.status !== "resolved" && (
            <ConfirmButton
              disabled={resolve.isPending}
              onConfirm={() => resolve.mutate(undefined)}
            >
              Resolve incident
            </ConfirmButton>
          )}
        </div>
        <h3>Detection evidence</h3>
        <Json value={i.evidence} />
        <h3>Incident timeline</h3>
        <ol className="timeline">
          {i.timeline.map((t: any, n: number) => (
            <li key={n}>
              <strong>{t.action}</strong>
              <p>
                {stamp(t.at)} · {t.actor}
              </p>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
export function EventSubmit({ projectId }: { projectId: string }) {
  const [pending, setPending] = useState(false);
  const { canOperate } = usePermissions();
  const queryClient = useQueryClient();
  const [type, setType] = useState("order.created");
  const [payload, setPayload] = useState('{"order_id":"demo-001"}');
  const [error, setError] = useState("");
  const [id, setId] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pending || !canOperate) return;
    setError("");
    let parsed;
    try {
      parsed = JSON.parse(payload);
    } catch {
      setError("Payload must be valid JSON.");
      return;
    }
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      setError("Payload must be a JSON object.");
      return;
    }
    setPending(true);
    try {
      const result = await api(
        "/events",
        "POST",
        { project_id: projectId, type, payload: parsed },
        { "Idempotency-Key": crypto.randomUUID() },
      );
      setId(result.id);
      void queryClient.invalidateQueries();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <ActionForm onSubmit={submit} className="form">
      <h3>Submit an event</h3>
      <label>
        Event type
        <input
          required
          value={type}
          onChange={(e) => setType(e.target.value)}
        />
      </label>
      <label>
        JSON payload
        <textarea
          required
          rows={5}
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
        />
      </label>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      <button className="primary" disabled={!projectId || pending}>
        {pending ? "Submitting…" : "Submit event"}
      </button>
      {id && (
        <p role="status">
          Event accepted. <Link to={`/events/${id}`}>View delivery</Link>
        </p>
      )}
    </ActionForm>
  );
}
