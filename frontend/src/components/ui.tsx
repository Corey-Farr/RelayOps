import { usePermissions } from "./access";
import {
  createContext,
  useContext,
  useState,
  useRef,
  useId,
  useEffect,
  type ReactNode,
  Component,
  type ErrorInfo,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
const ToastContext = createContext<(text: string) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState("");
  return (
    <ToastContext.Provider value={setMessage}>
      {children}
      {message && (
        <div className="toast" role="status">
          {message}
          <button
            aria-label="Dismiss notification"
            onClick={() => setMessage("")}
          >
            ×
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}
export function useAction(path: string, method = "POST") {
  const client = useQueryClient();
  const { canOperate, canAdmin } = usePermissions();
  const allowed = /^\/(projects|keys)(\/|$)/.test(path) ? canAdmin : canOperate;
  const toast = useContext(ToastContext);
  return useMutation({
    mutationFn: (body?: unknown) =>
      allowed
        ? api(path, method, body)
        : Promise.reject(new Error("Your role does not permit this action.")),
    onSuccess: () => {
      void client.invalidateQueries();
      toast("Change saved successfully.");
    },
    onError: (e: Error) => toast(e.message),
  });
}
export function Status({ value }: { value: string }) {
  return (
    <span className={`status ${value}`}>{value.replaceAll("_", " ")}</span>
  );
}
export function Empty({
  children = "No records yet. Data will appear as events flow through your system.",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">◎</span>
      <p>{children}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div aria-label="Loading" className="skeletons">
      <div />
      <div />
      <div />
    </div>
  );
}
export function Failure({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error">
      <strong>Unable to load this view</strong>
      <p>{error.message}</p>
      {retry && <button onClick={retry}>Try again</button>}
    </div>
  );
}
export function PageTitle({
  eyebrow = "OPERATIONS",
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </header>
  );
}
export function ConfirmButton({
  children,
  onConfirm,
  disabled = false,
}: {
  children: ReactNode;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { canOperate } = usePermissions();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (open) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  }, [open]);
  return (
    <>
      <button disabled={disabled || !canOperate} onClick={() => setOpen(true)}>
        {children}
      </button>
      <dialog
        ref={dialogRef}
        onCancel={() => setOpen(false)}
        onClose={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const buttons = dialogRef.current?.querySelectorAll("button");
          if (!buttons?.length) return;
          const first = buttons[0];
          const last = buttons[buttons.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
        aria-labelledby={titleId}
        className="modal"
      >
        <h2 id={titleId}>Confirm {children}</h2>
        <p>This changes live system state. Continue with this action?</p>
        <div className="actions">
          <button autoFocus onClick={() => setOpen(false)}>
            Cancel
          </button>
          <button
            className="primary"
            onClick={() => {
              onConfirm();
              setOpen(false);
            }}
          >
            Confirm
          </button>
        </div>
      </dialog>
    </>
  );
}
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(
      "Console rendering failed",
      error.message,
      info.componentStack,
    );
  }
  render() {
    return this.state.error ? (
      <Failure
        error={this.state.error}
        retry={() => window.location.reload()}
      />
    ) : (
      this.props.children
    );
  }
}
export function Json({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}
export function Pager({
  page,
  setPage,
  total,
  size = 10,
}: {
  page: number;
  setPage: (n: number) => void;
  total: number;
  size?: number;
}) {
  const lastPage = Math.max(0, Math.ceil(total / size) - 1);
  useEffect(() => {
    if (page > lastPage) setPage(lastPage);
  }, [page, lastPage, setPage]);
  return (
    <div className="pager">
      <span>
        {total} records · Page {page + 1} of{" "}
        {Math.max(1, Math.ceil(total / size))}
      </span>
      <div>
        <button disabled={page === 0} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <button
          disabled={(page + 1) * size >= total}
          onClick={() => setPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
