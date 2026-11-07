let csrf = "";
export type Session = { csrf: string; user: { id: string; name: string }; mode: string };
let bootstrapPromise: Promise<Session> | undefined;
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function clearSession() {
  csrf = "";
  bootstrapPromise = undefined;
}

export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Hapic-CSRF": csrf,
      ...options.headers,
    },
  });
  if (response.status === 401 && !path.startsWith("/auth/")) {
    clearSession();
    window.dispatchEvent(new Event("hapic:unauthorized"));
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      response.status >= 500
        ? "Ocurrió un error interno en el servidor. Recarga la página o vuelve a intentarlo."
        : response.ok
          ? "El servidor devolvió una respuesta no válida. Recarga la página."
          : `No se pudo completar la solicitud (HTTP ${response.status}).`,
      response.status,
    );
  }
  if (!response.ok) {
    throw new ApiError(
      data && typeof data.detail === "string"
        ? data.detail
        : "No se pudo completar la solicitud. Revisa los campos.",
      response.status,
    );
  }
  return data;
}
export function bootstrap() {
  return (bootstrapPromise ??= api<Session>("/bootstrap")
    .then((data) => {
      csrf = data.csrf;
      return data;
    })
    .catch((error) => {
      bootstrapPromise = undefined;
      throw error;
    }));
}
export const post = <T = any>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
export const put = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });

export type Org = { id: string; name: string };
export type Project = {
  id: string;
  name: string;
  organization_id: string;
  created_at: string;
};
export type Agent = {
  id: string;
  name: string;
  organization_id: string;
  project_id: string;
  kind: "ux" | "hapic" | "graphic-designer" | "architect" | "coder" | "community-manager";
  planner_id: string | null;
  model: string;
  effort: string;
  status: string;
  container_id: string | null;
  error: string | null;
  created_at: string;
};
export type State = {
  organizations: Org[];
  projects: Project[];
  agents: Agent[];
  settings: { model: string; effort: string };
};
export type Capabilities = {
  docker: { available: boolean; message: string; image: string };
  openai: { configured: boolean; source: string };
};
export type Template = {
  kind: Exclude<Agent["kind"], "hapic">;
  role: string;
  name: string;
  version: string;
  description: string;
  capabilities: string[];
  questions: string[];
  deliverables: string[];
  evidence_policy: string;
  instructions: string;
  recommended_model?: string;
  recommended_effort?: string;
  model_guidance?: string;
};
export type FileNode = {
  name: string;
  path: string;
  type: string;
  children?: FileNode[];
  preview?: boolean;
  size?: number;
  media_type?: "image" | "video" | "text";
};

export const agentRoles: Record<Agent["kind"], string> = {
  hapic: "Orquestador", ux: "Especialista UX", "graphic-designer": "Diseñador gráfico", architect: "Arquitecto / Planner", coder: "Coder", "community-manager": "Community Manager",
};
export function imageUrl(projectId: string, path: string, download = false) {
  return `/api/projects/${projectId}/image?path=${encodeURIComponent(path)}${download ? "&download=true" : ""}`;
}
export function videoUrl(projectId: string, path: string, download = false) {
  return `/api/projects/${projectId}/video?path=${encodeURIComponent(path)}${download ? "&download=true" : ""}`;
}
export type Attachment = { id: string; path: string; name: string; url: string; mime_type: string };
export type Message = { id: number; role: string; content: string; source: string; attachments?: Attachment[] };

export type IntegrationTool = {
  id: string;
  name: string;
  description: string;
  provider: string;
  access: "read" | "read-and-upload" | "generate" | "execute";
  requires_connection: boolean;
  actions: string[];
};
export type Connection = {
  id: string;
  project_id: string;
  provider: string;
  account_id: string;
  account_name: string;
  scopes: string[];
  status: "connected" | "reauthorization_required";
};
export type ToolAssignment = {
  agent_id: string;
  tool_id: string;
  enabled: number;
  connection_id: string | null;
};
export type ProjectTools = { connections: Connection[]; assignments: ToolAssignment[] };
export type YouTubeSettings = { configured: boolean; source: "file" | "server" | "none"; redirect_uri: string; scopes: string[]; message?: string };
export type YouTubeVideo = {
  id: string;
  title: string;
  published_at: string | null;
  privacy_status: string;
  statistics: Record<string, string>;
};
export type YouTubeVideos = { videos: YouTubeVideo[]; next_page_token: string | null; fetched_at: string };
export type HeyGenVideo = {
  id: string;
  agent_id: string;
  connection_id: string;
  status: "submitting" | "submission_unknown" | "pending" | "processing" | "completed" | "failed" | "cancelled";
  duration: number;
  resolution: string;
  aspect_ratio: string;
  estimated_cost_usd: string;
  saved: boolean;
  path: string | null;
  error: string | null;
  created_at: string;
};
