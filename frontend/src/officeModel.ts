import type { Agent, Project } from "./api";

export type OfficeExecution = {
  busy: boolean;
  active_tasks: number;
  queued_tasks: number;
  busy_agents?: string[];
  tasks?: { agent_id: string; objective: string; state: string; executing: boolean }[];
};
export type OfficePresence = {
  label: string;
  detail: string;
  tone: "working" | "idle" | "waiting" | "offline" | "unknown";
  working: boolean;
};
const roles = ["hapic", "architect", "coder", "ux", "graphic-designer", "community-manager"];
export const officeColors: Record<Agent["kind"], string> = {
  hapic: "#d7b77b", architect: "#ac9ad7", coder: "#84acd6", ux: "#7ab8ab",
  "graphic-designer": "#d89590", "community-manager": "#abc18b",
};

export function officeMembers(project: Project, agents: Agent[]) {
  return agents.filter(a => a.project_id === project.id && a.organization_id === project.organization_id)
    .sort((a, b) => roles.indexOf(a.kind) - roles.indexOf(b.kind) || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}

export function officeLayout(count: number) {
  const columns = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(count))));
  const rows = Math.max(2, Math.ceil(count / columns));
  const width = columns * 2.8 + 5.4;
  const depth = rows * 3.1 + 2;
  return {
    width, depth, columns,
    seats: Array.from({ length: count }, (_, i) => ({
      x: -width / 2 + 1.8 + (i % columns) * 2.8,
      z: -depth / 2 + 2 + Math.floor(i / columns) * 3.1,
    })),
  };
}

export function officePresence(agent: Agent, execution?: OfficeExecution): OfficePresence {
  const tasks = execution?.tasks?.filter(t => t.agent_id === agent.id) || [];
  const active = tasks.find(t => t.state === "running" && t.executing);
  const busy = execution?.busy_agents?.includes(agent.id) || (agent.kind === "hapic" && execution?.busy);
  if (active || busy) return { label: "Trabajando", detail: active?.objective || "Turno en ejecución", tone: "working", working: true };
  if (!execution) return { label: "Sin confirmar", detail: "El estado de ejecución no está disponible.", tone: "unknown", working: false };
  const pending = tasks.find(t => t.state === "running" || t.state === "queued" || t.state === "blocked");
  if (pending) return { label: pending.state === "running" ? "Revisar ejecución" : pending.state === "queued" ? "En cola" : "Tarea bloqueada", detail: pending.objective, tone: "waiting", working: false };
  if (agent.status === "provisioning") return { label: "Preparando runtime", detail: "El runtime se está preparando.", tone: "waiting", working: false };
  if (agent.status !== "running") return { label: agent.status === "error" ? "Error de runtime" : agent.status === "blocked" ? "Requiere configuración" : "Runtime sin iniciar", detail: "Abre la conversación para consultar o iniciar el runtime.", tone: "offline", working: false };
  return { label: "Sin ejecución activa", detail: "No hay un turno ni una tarea en ejecución confirmada.", tone: "idle", working: false };
}
