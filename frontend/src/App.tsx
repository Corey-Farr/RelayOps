import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Box,
  FlaskConical,
  Gauge,
  Layers,
  LogOut,
  Menu,
  Radio,
  Settings as SettingsIcon,
  ShieldAlert,
  Workflow,
  X,
} from "lucide-react";
import { api, ApiError, setCsrf, type Session } from "./services/api";
import { ErrorBoundary, Failure, Loading } from "./components/ui";
import {
  Overview,
  Workers,
  Events,
  EventDetail,
  DeadLetters,
  Incidents,
  IncidentDetail,
} from "./pages/Operations";
import {
  Lab,
  Policies,
  Settings,
  Login,
  DestinationPage,
} from "./pages/Controls";
const nav = [
  ["/destinations", "Destinations", Box],
  ["/", "Overview", Gauge],
  ["/events", "Event explorer", Layers],
  ["/dead-letters", "Dead letters", Box],
  ["/workers", "Worker pools", Radio],
  ["/incidents", "Incidents", ShieldAlert],
  ["/lab", "Reliability lab", FlaskConical],
  ["/policies", "Release policies", Workflow],
  ["/settings", "Settings", SettingsIcon],
] as const;
export function App() {
  const client = useQueryClient();
  const location = useLocation();
  const [menu, setMenu] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/me"),
    retry: false,
    staleTime: 60000,
  });
  useEffect(() => {
    setCsrf(session.data?.csrf_token || "");
  }, [session.data]);
  useEffect(() => {
    setMenu(false);
  }, [location.pathname]);
  if (session.isPending)
    return (
      <div className="auth-loading">
        <Loading />
      </div>
    );
  if (session.error) {
    if (session.error instanceof ApiError && session.error.status === 401)
      return <Login onLogin={() => void session.refetch()} />;
    return (
      <Failure error={session.error} retry={() => void session.refetch()} />
    );
  }
  if (!session.data) return null;
  const user = session.data.user;
  async function logout() {
    try {
      await api("/auth/logout", "POST");
      client.clear();
      window.location.assign("/");
    } catch (e) {
      setLogoutError((e as Error).message);
    }
  }
  return (
    <div className="app">
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <NavLink className="brand" to="/">
          <span className="brand-icon">
            <Activity size={23} />
          </span>
          RelayOps<span className="brand-dot">●</span>
        </NavLink>
        <div className="workspace">
          <span className="workspace-avatar">R</span>
          <div>
            <strong>Operations workspace</strong>
            <small>Local environment</small>
          </div>
          <span className="environment-dot" />
        </div>
        <div className="nav-label">CONTROL CENTER</div>
        <nav aria-label="Primary navigation">
          {nav.map(([path, label, Icon]) => (
            <NavLink end={path === "/"} key={path} to={path}>
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="engine-card">
            <span className="live-dot">Durable by design</span>
            <p>
              At-least-once delivery.
              <br />
              Built for recovery.
            </p>
          </div>
          <div className="user">
            <div className="avatar">{user.email[0].toUpperCase()}</div>
            <div>
              <strong title={user.email}>{user.email}</strong>
              <small>{user.role}</small>
            </div>
            <button aria-label="Sign out" onClick={() => void logout()}>
              <LogOut size={17} />
            </button>
          </div>
          {logoutError && <p role="alert">{logoutError}</p>}
        </div>
      </aside>
      {menu && (
        <button
          className="mobile-overlay"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="main-shell">
        <div className="topbar">
          <div className="row">
            <button
              className="menu-toggle"
              aria-label="Toggle navigation"
              onClick={() => setMenu(!menu)}
            >
              {menu ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="breadcrumb">
              Workspace <span>/</span>{" "}
              <strong>
                {nav.find(([p]) =>
                  p === "/"
                    ? location.pathname === "/"
                    : location.pathname.startsWith(p),
                )?.[1] || "Details"}
              </strong>
            </span>
          </div>
          <div className="topbar-meta">
            <span className="live-dot">Polling every 5s</span>
            <span className="tag">LOCAL DEMO</span>
          </div>
        </div>
        <main id="main-content">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/events" element={<Events />} />
              <Route path="/events/:id" element={<EventDetail />} />
              <Route path="/dead-letters" element={<DeadLetters />} />
              <Route path="/workers" element={<Workers />} />
              <Route path="/incidents" element={<Incidents />} />
              <Route path="/incidents/:id" element={<IncidentDetail />} />
              <Route path="/lab" element={<Lab />} />
              <Route path="/policies" element={<Policies />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/destinations" element={<DestinationPage />} />
              <Route
                path="*"
                element={
                  <Failure
                    error={
                      new Error(
                        "Page not found. Use the navigation to return to an operational view.",
                      )
                    }
                  />
                }
              />
            </Routes>
          </ErrorBoundary>
          <footer className="main-footer">
            <span>RelayOps / Event delivery infrastructure</span>
            <span>
              All metrics reflect recorded system activity{" "}
              <ArrowUpRight size={12} />
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
