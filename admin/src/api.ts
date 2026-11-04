/**
 * Client for `/api/admin/*`. Spec section 9.2.
 *
 * Rules:
 * - Every write carries `X-Requested-With: admin`. The API rejects writes without it.
 * - The Cloudflare Access cookie rides along on its own (same origin).
 * - An expired Access session shows up as a redirect to the login page, or as a 401 or 403.
 *   Those become `ApiError` with `sessionExpired = true`. The fix is a page reload.
 */
import type {
  AdminEdge,
  AdminImage,
  AdminProject,
  AdminProjectList,
  ImagePatch,
  Lead,
  LeadKind,
  LeadList,
  LeadStatus,
  MapPosition,
  ProjectInput,
  Publish,
  Summary,
} from "./types";

const BASE = "/api/admin";
const SESSION_MESSAGE = "Your admin login expired. Reload the page to log in again.";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body: unknown = null,
    readonly sessionExpired = false,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ValidationItem {
  loc?: (string | number)[];
  msg?: string;
}

/** FastAPI sends `detail` as a string, or as a list of field errors on a 422. */
function detailText(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationItem[])
      .map((d) => `${String(d.loc?.at(-1) ?? "request")}: ${d.msg ?? "invalid"}`)
      .join(". ");
  }
  return `Request failed with HTTP ${status}.`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-Requested-With"] = "admin";
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: payload,
      credentials: "same-origin",
      redirect: "manual",
    });
  } catch {
    // Access answers an expired session with a cross-origin redirect, which fetch reports
    // as a network error. A real network drop looks the same, and a reload fixes both.
    throw new ApiError(0, `Network error on ${method} ${path}. ${SESSION_MESSAGE}`, null, true);
  }
  if (res.type === "opaqueredirect" || res.status === 401) {
    throw new ApiError(res.status, SESSION_MESSAGE, null, true);
  }
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const message = detailText(data, res.status);
    const expired = res.status === 403 && message === "Admin login required.";
    throw new ApiError(res.status, expired ? SESSION_MESSAGE : message, data, expired);
  }
  return data as T;
}

export const api = {
  me: () => request<{ email: string }>("GET", "/me"),
  summary: () => request<Summary>("GET", "/summary"),

  projects: () => request<AdminProjectList>("GET", "/projects"),
  project: (id: number) => request<AdminProject>("GET", `/projects/${id}`),
  createProject: (input: ProjectInput) => request<AdminProject>("POST", "/projects", input),
  updateProject: (id: number, input: Partial<ProjectInput>) =>
    request<AdminProject>("PATCH", `/projects/${id}`, input),
  deleteProject: (id: number) => request<void>("DELETE", `/projects/${id}`),
  saveOrder: (ids: number[]) => request<void>("PUT", "/projects/order", { ids }),
  moveProject: (id: number, at: MapPosition) => request<AdminProject>("PATCH", `/projects/${id}`, at),
  saveEdges: (edges: AdminEdge[]) => request<{ edges: AdminEdge[] }>("PUT", "/edges", { edges }),

  uploadImage: (projectId: number, file: File, alt: string, caption: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("alt", alt);
    if (caption.trim()) form.append("caption", caption);
    return request<AdminImage>("POST", `/projects/${projectId}/images`, form);
  },
  uploadDiagram: (projectId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<AdminProject>("PUT", `/projects/${projectId}/diagram`, form);
  },
  updateImage: (id: number, patch: ImagePatch) =>
    request<AdminImage>("PATCH", `/images/${id}`, patch),
  deleteImage: (id: number) => request<void>("DELETE", `/images/${id}`),

  leads: (filters: { kind?: LeadKind | null; status?: LeadStatus | null; limit?: number }) => {
    const q = new URLSearchParams();
    if (filters.kind) q.set("kind", filters.kind);
    if (filters.status) q.set("status", filters.status);
    q.set("limit", String(filters.limit ?? 200));
    return request<LeadList>("GET", `/leads?${q}`);
  },
  setLeadStatus: (id: number, status: LeadStatus) =>
    request<Lead>("PATCH", `/leads/${id}`, { status }),

  publish: () => request<Publish>("POST", "/publish"),
};

/** The unscrubbed image ids from a 409 publish response, else null. */
export function blockedImageIds(err: unknown): number[] | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const ids = (err.body as { image_ids?: unknown } | null)?.image_ids;
  return Array.isArray(ids) ? ids.filter((i): i is number => typeof i === "number") : null;
}

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
