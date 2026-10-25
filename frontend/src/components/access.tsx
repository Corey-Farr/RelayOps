import {
  createContext,
  useContext,
  type ReactNode,
  type ComponentProps,
} from "react";
import type { User } from "../services/api";
// This is presentation gating; the API remains the authorization boundary.
export const RoleContext = createContext<User["role"]>("viewer");
export function usePermissions() {
  const role = useContext(RoleContext);
  return {
    canOperate: role === "admin" || role === "operator",
    canAdmin: role === "admin",
  };
}
export function ActionForm({
  admin = false,
  children,
  ...props
}: ComponentProps<"form"> & { admin?: boolean }) {
  const permissions = usePermissions();
  const allowed = admin ? permissions.canAdmin : permissions.canOperate;
  return (
    <form
      {...props}
      onSubmit={(e) => {
        if (!allowed) {
          e.preventDefault();
          return;
        }
        props.onSubmit?.(e);
      }}
    >
      <fieldset disabled={!allowed} className="action-fields">
        {children}
      </fieldset>
      {!allowed && (
        <p className="note">
          {admin ? "Administrator" : "Operator"} access required to make
          changes.
        </p>
      )}
    </form>
  );
}
export function AdminOnly({ children }: { children: ReactNode }) {
  return usePermissions().canAdmin ? (
    <>{children}</>
  ) : (
    <p className="note">API key management requires administrator access.</p>
  );
}
