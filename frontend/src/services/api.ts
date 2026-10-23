export type User = {id:string; email:string; role:'admin'|'operator'|'viewer'};
export type Session = {user:User; csrf_token:string};
let csrf = '';
export function setCsrf(value:string) { csrf = value; }
export class ApiError extends Error { constructor(public status:number, message:string) { super(message); } }
export async function api<T = any>(path:string, method = 'GET', body?:unknown, headers:Record<string,string> = {}):Promise<T> {
 const response = await fetch(`/api${path}`, { method, credentials:'same-origin', headers:{'Content-Type':'application/json', ...(method !== 'GET' ? {'X-CSRF-Token':csrf} : {}), ...headers}, body:body === undefined ? undefined : JSON.stringify(body) });
 const data = response.status === 204 ? null : await response.json().catch(() => null);
 if (!response.ok) { const detail=data?.detail; throw new ApiError(response.status, typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e:{msg:string})=>e.msg).join('; ') : `Request failed (${response.status})`); }
 return data as T;
}
export const stamp = (s?:string|null) => s ? new Date(s).toLocaleString() : '—';
export const percent = (n?:number|null) => n == null ? 'Insufficient data' : `${(n*100).toFixed(1)}%`;
