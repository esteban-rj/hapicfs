import React, { lazy, Suspense, useCallback, useEffect, useState, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  ArrowUpRight,
  Box,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  Database,
  FileText,
  Folder,
  FolderPlus,
  LayoutGrid,
  Layers,
  LoaderCircle,
  Megaphone,
  MessageSquareText,
  Moon,
  Palette,
  PenTool,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  SunMedium,
  Wrench,
  X,
} from "lucide-react";
import {
  api,
  bootstrap,
  post,
  put,
  agentRoles,
  imageUrl,
  videoUrl,
  type Agent,
  type Capabilities,
  type FileNode,
  type Project,
  type State,
  type Template,
} from "./api";
import {
  Badge,
  Chat,
  Empty,
  Mark,
  Modal,
  TemplateCard,
  Tree,
  CreateAgentModal,
  ImagePreview,
  VideoPreview,
} from "./components";
import "./style.css";
import { ModelSelect } from "./ModelSelect";
import { ToolsPanel } from "./ToolsPanel";
import { TeamDemo } from "./TeamDemo";

const ProjectOffice = lazy(() => import("./ProjectOffice"));

type TeamTask = { id: string; agent_id: string; agent_name: string; objective: string; state: string; executing: boolean; latest_activity: string | null };
type TeamExecution = { busy: boolean; active_tasks: number; queued_tasks: number; tasks?: TeamTask[]; busy_agents?: string[] };

type Page =
  | "Resumen"
  | "Proyectos"
  | "Agentes"
  | "Plantillas"
  | "Herramientas"
  | "Configuración";
const nav = [
  { name: "Resumen" as Page, icon: LayoutGrid },
  { name: "Proyectos" as Page, icon: Layers },
  { name: "Agentes" as Page, icon: Sparkles },
  { name: "Plantillas" as Page, icon: Folder },
  { name: "Herramientas" as Page, icon: Wrench },
  { name: "Configuración" as Page, icon: Settings },
];
function App() {
  const [state, setState] = useState<State>();
  const [caps, setCaps] = useState<Capabilities>();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [createTemplate, setCreateTemplate] = useState<Template>();
  const [orgId, setOrgId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [officeProjectId, setOfficeProjectId] = useState("");
  const officeOpener = useRef<HTMLElement | null>(null);
  const closeOffice = useCallback(() => {
    setOfficeProjectId("");
    // Wait for both the lazy-loading dialog and the office dialog to close.
    requestAnimationFrame(() => {
      if (officeOpener.current?.isConnected) officeOpener.current.focus();
    });
  }, []);
  const [agentId, setAgentId] = useState("");
  const [page, setPage] = useState<Page>("Resumen");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [projectActivity, setProjectActivity] = useState<TeamExecution>();
  const [modal, setModal] = useState<"org" | "project" | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [tree, setTree] = useState<FileNode>();
  const [file, setFile] = useState<{
    path: string;
    content: string;
    size: number;
    media_type?: "image" | "video" | "text";
  }>();
  const [runtime, setRuntime] = useState<any>();
  const [events, setEvents] = useState<any[]>([]);
  const [tab, setTab] = useState<"Conversación" | "Archivos" | "Actividad">(
    "Conversación",
  );
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const [model, setModel] = useState("gpt-6.1-sol");
  const [effort, setEffort] = useState("xhigh");
  const [key, setKey] = useState("");
  const [darkMode, setDarkMode] = useState(false);
  const refresh = useCallback(async () => {
    const [s, c] = await Promise.all([
      api<State>("/state"),
      api<Capabilities>("/capabilities"),
    ]);
    setState(s);
    setCaps(c);
    setOrgId((id) =>
      s.organizations.some((o) => o.id === id)
        ? id
        : s.organizations[0]?.id || "",
    );
  }, []);
  useEffect(() => {
    bootstrap()
      .then(() =>
        Promise.all([
          refresh(),
          api<Template[]>("/templates").then(setTemplates),
        ]),
      )
      .catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    if (!state) return;
    const query = new URLSearchParams(window.location.search);
    const result = query.get("youtube");
    if (!result) return;
    setPage("Herramientas");
    if (result === "connected") {
      const returnedProject = state.projects.find((item) => item.id === query.get("project_id"));
      if (returnedProject) {
        setOrgId(returnedProject.organization_id);
        setProjectId(returnedProject.id);
      }
      setToast("Canal de YouTube conectado. Ya puedes asignarlo a tus agentes.");
    } else {
      setError("No se pudo completar la conexión con Google. Comprueba los usuarios de prueba, concede ambos permisos de lectura y vuelve a conectar el canal.");
    }
    window.history.replaceState(null, "", window.location.pathname);
  }, [state]);
  useEffect(() => {
    if (state?.settings) {
      setModel(state.settings.model);
      setEffort(state.settings.effort);
    }
  }, [state?.settings.model, state?.settings.effort]);
  const org = state?.organizations.find((o) => o.id === orgId);
  const projects =
    state?.projects.filter((p) => p.organization_id === orgId) || [];
  const project = projects.find((p) => p.id === projectId);
  const officeProject = projects.find((p) => p.id === officeProjectId);
  const agents =
    state?.agents.filter(
      (a) =>
        a.organization_id === orgId &&
        (!projectId || a.project_id === projectId),
    ) || [];
  const agent = agents.find((a) => a.id === agentId);
  const flowAgents = useMemo(() => {
    if (!projectId || !state) return [];
    return [...state.agents]
      .filter((item) => item.project_id === projectId)
      .sort((left, right) => {
        const rank = (item: (typeof state.agents)[number]) => {
          if (item.kind === "hapic") return 0;
          if (item.kind === "architect") return 1;
          if (item.kind === "coder") return 2;
          if (item.kind === "ux") return 3;
          if (item.kind === "graphic-designer") return 4;
          if (item.kind === "community-manager") return 5;
          return 6;
        };
        return rank(left) - rank(right);
      });
  }, [projectId, state]);
  const createDemoAgent = useCallback(async () => {
    if (busy) return;
    const targetProjectId = projectId || projects[0]?.id;
    if (!targetProjectId) {
      newModal(org ? "project" : "org");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const existing = state?.agents.find((item) => item.project_id === targetProjectId && item.kind === "ux" && item.name === "Agente de prueba");
      const created = existing ?? await post<Agent>("/projects/" + targetProjectId + "/agents", {
        name: "Agente de prueba",
        template: "ux",
      });
      await refresh();
      setProjectId(targetProjectId);
      setAgentId(created.id);
      setPage("Agentes");
      setTab("Conversación");
      setToast(existing ? "Agente de prueba cargado en el proyecto." : "Agente de prueba creado y cargado en el proyecto.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar el agente de prueba.");
    } finally {
      setBusy(false);
    }
  }, [org, projectId, projects, refresh, busy, state?.agents]);
  const loadProject = useCallback(
    (nextProjectId: string) => {
      const nextProject = state?.projects.find((item) => item.id === nextProjectId);
      if (!nextProject) return;
      setOrgId(nextProject.organization_id);
      setProjectId(nextProject.id);
      const hapic = state?.agents.find(
        (a) => a.project_id === nextProject.id && a.kind === "hapic",
      );
      setAgentId(hapic?.id || "");
      setTab("Conversación");
      setFile(undefined);
      setPage("Agentes");
      setToast("Proyecto cargado: " + nextProject.name);
    },
    [state],
  );

  const coordinator = state?.agents.find((item) => item.project_id === projectId && item.kind === "hapic");
  useEffect(() => {
    setProjectActivity(undefined);
    if (!coordinator) return;
    let active = true;
    let previouslyWorking: boolean | undefined;
    let timer: ReturnType<typeof setTimeout>;
    const coordinatorId = coordinator.id;
    async function poll() {
      try {
        const status = await api<TeamExecution>(`/agents/${coordinatorId}/execution`);
        if (active) {
          const working = status.busy || status.active_tasks > 0 || status.queued_tasks > 0;
          if (previouslyWorking && !working) setToast("La ejecución del equipo terminó. Consulta las tareas en Hapic para revisar el resultado.");
          previouslyWorking = working;
          setProjectActivity({...status, busy_agents: status.busy ? [coordinatorId] : []});
        }
      } catch { if (active) setProjectActivity(undefined); }
      if (active) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [coordinator?.id]);
  const directoryCoordinators = state?.agents.filter(a => a.organization_id === orgId && a.kind === "hapic").map(a => a.id).join(",") || "";
  useEffect(() => {
    if (page !== "Agentes" || agentId || projectId || !directoryCoordinators) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setProjectActivity(undefined);
    async function pollDirectory() {
      try {
        const combined: TeamExecution = {busy: false, active_tasks: 0, queued_tasks: 0, tasks: [], busy_agents: []};
        for (const id of directoryCoordinators.split(",")) {
          if (!active) return;
          const status = await api<TeamExecution>(`/agents/${id}/execution`);
          combined.busy ||= status.busy;
          combined.active_tasks += status.active_tasks;
          combined.queued_tasks += status.queued_tasks;
          combined.tasks!.push(...(status.tasks || []));
          if (status.busy) combined.busy_agents!.push(id);
        }
        if (active) setProjectActivity(combined);
      } catch { if (active) setProjectActivity(undefined); }
      if (active) timer = setTimeout(pollDirectory, 6000);
    }
    void pollDirectory();
    return () => { active = false; clearTimeout(timer); };
  }, [directoryCoordinators, page, projectId, agentId]);
  const toggleProject = useCallback((projectIdToToggle: string, expanded: boolean) => {
    setExpandedProjects((current) => ({
      ...current,
      [projectIdToToggle]: !expanded,
    }));
  }, []);
  useEffect(() => {
    if (projectId && !projects.some((p) => p.id === projectId)) {
      setProjectId("");
      setAgentId("");
    }
  }, [orgId, state?.projects, projectId]);
  useEffect(() => {
    if (!projectId) {
      setTree(undefined);
      return;
    }
    let active = true;
    api<FileNode>("/projects/" + projectId + "/tree")
      .then((t) => {
        if (active) setTree(t);
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [projectId, state?.agents.length]);
  useEffect(() => {
    if (!agentId) {
      setRuntime(undefined);
      return;
    }
    let active = true;
    const load = () =>
      Promise.all([
        api("/agents/" + agentId + "/runtime"),
        api<any[]>("/agents/" + agentId + "/events"),
      ])
        .then(([r, e]) => {
          if (active) {
            setRuntime(r);
            setEvents(e);
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    load();
    const timer = setInterval(() => {
      load();
      refresh().catch(() => {});
    }, 6000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [agentId, refresh]);
  useEffect(() => {
    if (tab !== "Archivos" || !projectId) return;
    let active = true;
    const load = () =>
      api<FileNode>("/projects/" + projectId + "/tree")
        .then((t) => {
          if (active) setTree(t);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    load();
    const timer = setInterval(load, 6000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [tab, projectId]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  function openProject(p: Project) {
    setProjectId(p.id);
    const h = state?.agents.find(
      (a) => a.project_id === p.id && a.kind === "hapic",
    );
    setAgentId(h?.id || "");
    setTab("Conversación");
    setFile(undefined);
    setPage("Agentes");
  }
  function openAgent(a: Agent) {
    setOfficeProjectId("");
    setProjectId(a.project_id);
    setAgentId(a.id);
    setPage("Agentes");
    setTab("Conversación");
    setFile(undefined);
  }
  function openOffice(p: Project) {
    officeOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (projectId !== p.id) setProjectActivity(undefined);
    setProjectId(p.id);
    setOfficeProjectId(p.id);
  }
  async function action(fn: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function newModal(kind: "org" | "project") {
    setName("");
    setProjectName("");
    setModal(kind);
  }
  async function create(e: React.FormEvent) {
    e.preventDefault();
    await action(async () => {
      if (modal === "org") {
        const o = await post("/organizations", { name });
        setOrgId(o.id);
        if (projectName.trim()) {
          const p = await post("/organizations/" + o.id + "/projects", {
            name: projectName,
          });
          setProjectId(p.id);
        }
      } else {
        const p = await post("/organizations/" + orgId + "/projects", { name });
        setProjectId(p.id);
      }
      await refresh();
      setModal(null);
      setToast("Tu espacio está listo.");
    });
  }
  async function readFile(n: FileNode) {
    if (n.media_type === "image" || n.media_type === "video") {
      setFile({ path: n.path, content: "", size: n.size || 0, media_type: n.media_type });
      return;
    }
    await action(async () =>
      setFile(
        await api(
          "/projects/" + projectId + "/file?path=" + encodeURIComponent(n.path),
        ),
      ),
    );
  }
  const start = () =>
    action(async () => {
      if (!agent) return;
      await post("/agents/" + agent.id + "/start");
      setRuntime({ status: "provisioning", ready: false });
      setToast(
        "Provisión solicitada. El estado se comprobará automáticamente.",
      );
      await refresh();
    });
  const title =
    page === "Agentes" && agent
      ? agent.name
      : page === "Resumen"
        ? "Tu equipo, ampliado."
        : page;
  const agentIcon = (kind: Agent["kind"]) => {
    switch (kind) {
      case "hapic":
        return <Mark small />;
      case "ux":
        return <PenTool size={12} />;
      case "graphic-designer":
        return <Palette size={12} />;
      case "architect":
        return <LayoutGrid size={12} />;
      case "coder":
        return <Code2 size={12} />;
      case "community-manager":
        return <Megaphone size={12} />;
      default:
        return <Sparkles size={12} />;
    }
  };
  return (
    <div className={darkMode ? "theme-dark" : "theme-light"}>
      <header className="topbar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Resumen");
          }}
        >
          <Mark small />
          <span>Hapic</span>
        </a>
        <span className="header-divider" />
        <div className="org-select">
          <Building2 size={16} />
          <select
            aria-label="Organización activa"
            value={orgId}
            onChange={(e) => {
              if (e.target.value === "__new") newModal("org");
              else setOrgId(e.target.value);
            }}
          >
            {!state?.organizations.length ? (
              <option value="">Tu organización</option>
            ) : null}
            {state?.organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
            <option value="__new">+ Nueva organización</option>
          </select>
          <ChevronDown size={13} />
        </div>
        <div className="breadcrumbs">
          <span>{org?.name || "Espacio local"}</span>
          <ChevronRight size={13} />
          {project ? (
            <>
              <button onClick={() => openProject(project)}>
                {project.name}
              </button>
              <ChevronRight size={13} />
            </>
          ) : null}
          <strong>{page === "Agentes" && agent ? agent.name : page}</strong>
        </div>
        <span className="local-tag">
          <i />
          Local
        </span>
        <button
          className="icon-button theme-toggle"
          aria-label="Cambiar tema"
          onClick={() => setDarkMode((value) => !value)}
          title="Cambiar tema"
        >
          {darkMode ? <SunMedium size={15} /> : <Moon size={15} />}
        </button>
        <div className="avatar" title="Operador local">
          Tú
        </div>
      </header>
      <aside className="sidebar">
        <nav>
          {nav.map(({ name: n, icon: Icon }) => (
            <button
              key={n}
              className={page === n ? "active" : ""}
              onClick={() => {
                setPage(n);
                setAgentId("");
                if (n !== "Agentes") {
                  setAgentId("");
                  if (n !== "Herramientas") setProjectId("");
                }
              }}
            >
              <Icon size={18} />
              {n}
              {n === "Plantillas" ? <span className="nav-count">{templates.length}</span> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-projects">
          <div className="eyebrow">
            TU ESPACIO
            <button
              className="icon-button"
              aria-label="Nuevo proyecto"
              onClick={() => newModal(org ? "project" : "org")}
            >
              <Plus size={14} />
            </button>
          </div>
          {projects.length > 0 ? (
            projects.map((p) => {
              const projectAgents = state?.agents.filter((a) => a.project_id === p.id) || [];
              const isExpanded = expandedProjects[p.id] ?? projectId === p.id;
              return (
                <div key={p.id} className="project-group">
                  <div className="project-nav-row">
                    <button className="project-disclosure icon-button" aria-label={(isExpanded ? "Contraer " : "Expandir ") + p.name} aria-expanded={isExpanded} onClick={() => toggleProject(p.id, isExpanded)}>
                      {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    </button>
                    <button className={"project-nav " + (projectId === p.id ? "current" : "")} onClick={() => openProject(p)}>
                      <Folder size={15} /><span>{p.name}</span><small>{projectAgents.length}</small>
                    </button>
                  </div>
                  {isExpanded ? (
                    <div className="agent-submenu">
                      <button className="project-office-link" onClick={() => openOffice(p)}>
                        <Box size={15} /> Oficina 3D
                      </button>
                      {projectAgents.length ? (
                        projectAgents.map((a) => (
                          <button
                            className={"agent-nav " + (a.id === agentId ? "current" : "")}
                            key={a.id}
                            onClick={() => openAgent(a)}
                          >
                            <span className="agent-icon">
                              {agentIcon(a.kind)}
                            </span>
                            {a.name}
                          </button>
                        ))
                      ) : (
                        <div className="agent-empty">Sin agentes</div>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })
          ) : (
            <p className="tiny muted">Tus proyectos aparecerán aquí.</p>
          )}
        </div>
        <div className="sidebar-footer">
          <div className="storage-line">
            <Database size={15} />
            <span>Estado persistente</span>
          </div>
          <p>Tu espacio de trabajo, en tu entorno.</p>
          <span className="version">MVP · 0.1</span>
        </div>
      </aside>
      <main>
        <div className="page-top">
          <div>
            <div className="eyebrow">
              {org?.name || "BIENVENIDO A HAPIC"}
              {project ? " / " + project.name : ""}
            </div>
            <h1>
              {title}
              {page === "Agentes" && agent ? (
                <span className="tag">
                  {agentRoles[agent.kind]}
                </span>
              ) : null}
            </h1>
            <p className="subtitle">
              {page === "Resumen" ? (
                "Un lugar para tus proyectos. Un equipo para llevarlos más lejos."
              ) : page === "Proyectos" ? (
                "Cada proyecto, con su propio contexto y equipo."
              ) : page === "Plantillas" ? (
                "Un punto de partida claro para cada especialista."
              ) : page === "Configuración" ? (
                "Conecta tu entorno y elige cómo trabaja Hapic."
              ) : page === "Herramientas" ? (
                "Conexiones que amplían lo que puede hacer tu equipo."
              ) : agent ? (
                <Badge status={runtime?.status || agent.status} />
              ) : (
                "Agentes con memoria, propósito y un espacio propio."
              )}
            </p>
          </div>
          <div className="page-actions">
            {project ? <button className="secondary" onClick={() => openOffice(project)}><Box size={16} /> Abrir oficina 3D</button> : null}
            {(page === "Resumen" || page === "Agentes") && (
              <>
                {projects.length ? (
                  <select
                    className="project-loader-select"
                    value={projectId || ""}
                    onChange={(e) => {
                      if (e.target.value) {
                        loadProject(e.target.value);
                      }
                    }}
                    aria-label="Proyecto cargado"
                  >
                    <option value="">Selecciona un proyecto</option>
                    {projects.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                ) : null}
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    projectId || projects[0]
                      ? createDemoAgent()
                      : newModal(org ? "project" : "org")
                  }
                >
                  <Sparkles size={15} />
                  Agente de prueba
                </button>
              </>
            )}
            {page === "Resumen" || page === "Proyectos" ? (
              <button
                className="primary"
                onClick={() => newModal(org ? "project" : "org")}
              >
                <Plus size={16} />
                {org ? "Nuevo proyecto" : "Crear mi espacio"}
              </button>
            ) : page === "Agentes" && agent ? (
              <button
                className="secondary"
                disabled={busy || runtime?.status === "provisioning"}
                onClick={start}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={15} />
                ) : (
                  <Box size={15} />
                )}
                {agent.container_id ? "Reiniciar runtime" : "Iniciar runtime"}
              </button>
            ) : null}
          </div>
        </div>
        {projectActivity && (projectActivity.busy || projectActivity.active_tasks > 0 || projectActivity.queued_tasks > 0) ? <div className="execution-status" role="status">
          <LoaderCircle className="spin" size={16} />
          <strong>Hapic y su equipo están trabajando · {projectActivity.active_tasks} en ejecución · {projectActivity.queued_tasks} en cola.</strong>
          <button className="text-button" onClick={() => { if (coordinator) { setAgentId(coordinator.id); setPage("Agentes"); setTab("Conversación"); } }}>Ver tareas</button>
        </div> : null}
        {error ? (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              aria-label="Cerrar error"
              className="icon-button"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        ) : null}
        {!state ? (
          <div className="loading">
            <LoaderCircle className="spin" size={22} />
            Cargando tu espacio…
          </div>
        ) : (
          <>
            {page === "Resumen" ? (
              <div className="overview-layout">
                <div>
                  <div className="metrics">
                    <div>
                      <Folder size={19} />
                      <strong>{projects.length}</strong>
                      <span>Proyectos</span>
                    </div>
                    <div>
                      <Sparkles size={19} />
                      <strong>
                        {agents.filter((a) => a.kind !== "hapic").length}
                      </strong>
                      <span>Especialistas</span>
                    </div>
                    <div>
                      <Layers size={19} />
                      <strong>{templates.length}</strong>
                      <span>Plantillas disponibles</span>
                    </div>
                  </div>
                  {!org ? (
                    <div className="onboarding">
                      <span className="eyebrow">DE UNA IDEA A UN EQUIPO</span>
                      <h2>
                        Todo empieza
                        <br />
                        con tu espacio.
                      </h2>
                      <p>
                        Crea una organización, abre tu primer proyecto y deja
                        que Hapic te ayude a sumar tu primer especialista.
                      </p>
                      <button
                        className="primary"
                        onClick={() => newModal("org")}
                      >
                        Crear organización <ArrowRight size={16} />
                      </button>
                      <div className="onboarding-steps">
                        <span>
                          <Building2 size={15} />
                          Organización
                        </span>
                        <ChevronRight size={13} />
                        <span>
                          <Folder size={15} />
                          Proyecto
                        </span>
                        <ChevronRight size={13} />
                        <span>
                          <Sparkles size={15} />
                          Agentes
                        </span>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="section-heading">
                        <h2>
                          Proyectos{" "}
                          <span className="count">{projects.length}</span>
                        </h2>
                        <button
                          className="text-button"
                          onClick={() => setPage("Proyectos")}
                        >
                          Ver todos <ArrowRight size={14} />
                        </button>
                      </div>
                      {projects.length ? (
                        <div className="project-grid">
                          {projects.slice(0, 4).map((p) => (
                            <ProjectCard
                              key={p.id}
                              project={p}
                              count={
                                state.agents.filter(
                                  (a) => a.project_id === p.id,
                                ).length
                              }
                              click={() => openProject(p)}
                              office={() => openOffice(p)}
                            />
                          ))}
                        </div>
                      ) : (
                        <Empty
                          icon={<FolderPlus size={25} />}
                          title="Tu primer proyecto te espera"
                          action={
                            <button
                              className="secondary"
                              onClick={() => newModal("project")}
                            >
                              <Plus size={15} />
                              Crear proyecto
                            </button>
                          }
                        >
                          Dale un espacio a esa idea que quieres construir.
                        </Empty>
                      )}
                      <div className="section-heading">
                        <h2>Agentes</h2>
                        <button
                          className="text-button"
                          onClick={() => setPage("Agentes")}
                        >
                          Ver todos <ArrowRight size={14} />
                        </button>
                      </div>
                      <AgentTable
                        agents={agents}
                        projects={projects}
                        open={openAgent}
                      />
                    </>
                  )}
                  <div className="environment-strip">
                    <span>
                      <span
                        className={
                          "connection-dot " +
                          (caps?.docker.available ? "ok" : "")
                        }
                      />
                      Docker{" "}
                      {caps?.docker.available ? "conectado" : "pendiente"}
                    </span>
                    <span>
                      <span
                        className={
                          "connection-dot " +
                          (caps?.openai.configured ? "ok" : "")
                        }
                      />
                      OpenAI{" "}
                      {caps?.openai.configured ? "configurado" : "pendiente"}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => setPage("Configuración")}
                    >
                      Configurar <ArrowUpRight size={13} />
                    </button>
                  </div>
                </div>
                <aside className="hapic-panel card">
                  <div className="card-heading">
                    <Mark small />
                    <strong>Hapic</strong>
                    <span className="tag">Orquestador</span>
                  </div>
                  <div className="hapic-panel-body">
                    <div className="orb">
                      <Mark />
                    </div>
                    <h2>
                      Una idea.
                      <br />
                      Muchas posibilidades.
                    </h2>
                    <p>
                      Hapic conecta el contexto de tu proyecto con el
                      especialista que necesitas.
                    </p>
                    <button
                      className="primary"
                      onClick={() =>
                        projects.length
                          ? openProject(projects[0])
                          : newModal(org ? "project" : "org")
                      }
                    >
                      <Sparkles size={16} />
                      {projects.length
                        ? "Conversar con Hapic"
                        : "Comenzar con Hapic"}
                    </button>
                    <div className="panel-features">
                      <span>
                        <Database size={15} />
                        Memoria entre sesiones
                      </span>
                      <span>
                        <Folder size={15} />
                        Archivos persistentes
                      </span>
                      <span>
                        <ShieldCheck size={15} />
                        Contexto por proyecto
                      </span>
                    </div>
                  </div>
                  <div className="hapic-panel-footer">
                    <span className="tiny">{state.settings.model}</span>
                    <span className="tag">{state.settings.effort}</span>
                  </div>
                </aside>
              </div>
            ) : null}
            {page === "Proyectos" ? (
              projects.length ? (
                <div className="project-grid wide">
                  {projects.map((p) => (
                    <ProjectCard
                      key={p.id}
                      project={p}
                      count={
                        state.agents.filter((a) => a.project_id === p.id).length
                      }
                      click={() => openProject(p)}
                      office={() => openOffice(p)}
                    />
                  ))}
                  <button
                    className="new-project-card"
                    onClick={() => newModal("project")}
                  >
                    <Plus size={22} />
                    <span>Nuevo proyecto</span>
                  </button>
                </div>
              ) : (
                <Empty
                  icon={<FolderPlus size={28} />}
                  title="Un espacio para construir"
                  action={
                    <button
                      className="primary"
                      onClick={() => newModal(org ? "project" : "org")}
                    >
                      Crear {org ? "proyecto" : "organización"}{" "}
                      <Plus size={15} />
                    </button>
                  }
                >
                  Organiza el contexto, los archivos y los agentes de tu próxima
                  idea.
                </Empty>
              )
            ) : null}
            {page === "Agentes" ? (
              agent ? (
                <>
                  <button className="text-button team-back" onClick={() => setAgentId("")}><ChevronRight size={14} /> Volver al equipo</button>
                  <div className="tabs">
                    {(["Conversación", "Archivos", "Actividad"] as const).map(
                      (t) => (
                        <button
                          key={t}
                          className={tab === t ? "active" : ""}
                          onClick={() => setTab(t)}
                        >
                          {t}
                        </button>
                      ),
                    )}
                    <span className="tab-fill" />
                    <code>{agent.id}</code>
                  </div>
                  {tab === "Conversación" ? (
                    <div className="agent-layout">
                      <Chat
                        key={agent.id}
                        agent={agent}
                        connected={
                          !!runtime?.ready && !!caps?.openai.configured
                        }
                        changed={refresh}
                        onSettings={() => setPage("Configuración")}
                        templates={templates}
                        onPrepare={(kind) => setCreateTemplate(templates.find((t) => t.kind === kind))}
                      />
                      <div className="agent-side">
                        {agent.kind !== "hapic" && templates.find((t) => t.kind === agent.kind) ? (
                          <TemplateCard template={templates.find((t) => t.kind === agent.kind)!} compact />
                        ) : (
                          <div className="card compact-card">
                            <Sparkles size={20} />
                            <h3>Un equipo para tu proyecto</h3>
                            <p>
                              UX, diseño gráfico, arquitectura, código y community management. El community manager prepara contenido para Instagram y YouTube.
                            </p>
                          </div>
                        )}
                        {agent.planner_id ? <div className="card compact-card"><h3>Arquitecto vinculado</h3><p>{state.agents.find((a) => a.id === agent.planner_id)?.name}</p><p>Lee su plan publicado antes de escribir código.</p></div> : null}
                        <button className="secondary" onClick={() => setPage("Plantillas")}><Plus size={15} /> Añadir especialista</button>
                        <div className="card flow-card">
                          <div className="card-title">
                            <Layers size={17} />
                            Flujo de agentes
                          </div>
                          <div className="flow-list">
                            {flowAgents.length ? (
                              flowAgents.map((item, index) => (
                                <div key={item.id} className="flow-item">
                                  <div className="flow-connector">
                                    {index < flowAgents.length - 1 ? <span /> : null}
                                  </div>
                                  <button
                                    className={"flow-node " + (item.id === agentId ? "active" : "")}
                                    onClick={() => openAgent(item)}
                                  >
                                    <span className="agent-letter small-letter">
                                      {item.kind === "hapic" ? "H" : item.name[0].toUpperCase()}
                                    </span>
                                    <div>
                                      <strong>{item.name}</strong>
                                      <small>{agentRoles[item.kind]}</small>
                                    </div>
                                  </button>
                                </div>
                              ))
                            ) : (
                              <p className="muted flow-empty">Sin agentes en este proyecto aún.</p>
                            )}
                          </div>
                        </div>
                        <RuntimeCard agent={agent} runtime={runtime} />
                      </div>
                    </div>
                  ) : tab === "Archivos" ? (
                    <div className="files-layout">
                      <section className="card file-tree">
                        <div className="card-title">
                          <Folder size={16} />
                          Estructura real
                          <button
                            className="icon-button"
                            aria-label="Actualizar árbol"
                            onClick={() =>
                              api<FileNode>("/projects/" + projectId + "/tree")
                                .then(setTree)
                                .catch((e) => setError(e.message))
                            }
                          >
                            <RefreshCw size={14} />
                          </button>
                        </div>
                        <div className="tree-scroll">
                          {tree ? (
                            <Tree
                              node={tree}
                              label={project?.name}
                              select={readFile}
                              selected={file?.path}
                            />
                          ) : (
                            <p className="muted">Leyendo carpetas…</p>
                          )}
                        </div>
                        <p className="tree-note">
                          Los secretos y logs están excluidos. Los archivos de
                          estado binarios no admiten vista previa.
                        </p>
                      </section>
                      <section className="card file-preview">
                        <div className="card-title">
                          <FileText size={16} />
                          {file ? file.path.split("/").pop() : "Vista previa"}
                          {file ? (
                            <span className="tiny muted">
                              {file.size.toLocaleString("es")} bytes
                            </span>
                          ) : null}
                        </div>
                        {file ? (
                          file.media_type === "video" ? <VideoPreview key={file.path} src={videoUrl(projectId, file.path)} name={file.path.split("/").pop() || "Vídeo del proyecto"} download={videoUrl(projectId, file.path, true)} /> : file.media_type === "image" ? <ImagePreview key={file.path} src={imageUrl(projectId, file.path)} alt={file.path.split("/").pop() || "Imagen del proyecto"} download={imageUrl(projectId, file.path, true)} /> : <pre>{file.content}</pre>
                        ) : (
                          <Empty
                            icon={<FileText size={28} />}
                            title="El contexto toma forma aquí"
                          >
                            Selecciona un archivo para ver su contenido. Los
                            entregables aparecerán cuando el agente los guarde.
                          </Empty>
                        )}
                      </section>
                      <RuntimeCard agent={agent} runtime={runtime} />
                    </div>
                  ) : (
                    <section className="card activity">
                      <div className="card-title">
                        <Clock3 size={17} />
                        Actividad del agente
                      </div>
                      {events.length ? (
                        events.map((event) => (
                          <div className="event" key={event.id}>
                            <span className="event-dot" />
                            <div>
                              <p>{event.message}</p>
                              <time>
                                {new Date(event.created_at).toLocaleString(
                                  "es-CO",
                                )}
                              </time>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="muted">Sin eventos todavía.</p>
                      )}
                    </section>
                  )}
                </>
              ) : (
                <>
                  <section className="team-hero" aria-labelledby="team-title">
                    <div><span className="eyebrow">PERSONAS + AGENTES</span><h2 id="team-title">Una idea. Todo tu equipo.</h2><p>Hapic coordina. Cada especialista aporta lo suyo. Aquí ves quién está en tu proyecto y en qué está trabajando.</p></div>
                    <button className="primary" onClick={() => coordinator ? openAgent(coordinator) : agents.find(a => a.kind === "hapic") ? openAgent(agents.find(a => a.kind === "hapic")!) : newModal(org ? "project" : "org")}><Sparkles size={16} /> {agents.length ? "Hablar con Hapic" : "Crear mi equipo"}<ArrowUpRight size={16} /></button>
                  </section>
                  <div className="team-metrics">
                    <div><Sparkles size={18} /><strong>{agents.length}</strong><span>Agentes en tu equipo</span></div>
                    <div><Clock3 size={18} /><strong>{projectActivity ? projectActivity.active_tasks + (projectActivity.busy_agents?.length ?? (projectActivity.busy ? 1 : 0)) : "—"}</strong><span>{project ? "Ejecuciones en este proyecto" : "Ejecuciones en tus proyectos"}</span></div>
                    <div><Layers size={18} /><strong>{projectActivity?.queued_tasks ?? "—"}</strong><span>Tareas en espera</span></div>
                  </div>
                  <div className="team-workspace">
                    <div className="team-directory">
                      <div className="section-heading"><div><h2>Tu equipo <span className="count">{agents.length}</span></h2><p className="muted tiny">Roles, tareas y acceso a cada conversación.</p></div>
                        <select className="team-project-filter" aria-label="Filtrar equipo por proyecto" value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">Todos los proyectos</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
                      </div>
                      <AgentTable agents={agents} projects={projects} open={openAgent} execution={projectActivity} />
                    </div>
                    <TeamDemo onStart={() => { const hapic = coordinator || agents.find(a => a.kind === "hapic"); if (hapic) openAgent(hapic); else newModal(org ? "project" : "org"); }} hasTeam={agents.length > 0} />
                  </div>
                </>
              )
            ) : null}
            {page === "Plantillas" && templates.length ? (
              <div className="templates-layout">
                <div className="template-catalog">{templates.map((item) => <TemplateCard key={item.kind} template={item} onUse={() => setCreateTemplate(item)} />)}</div>
                <div className="template-explanation">
                  <span className="eyebrow">
                    UN PUNTO DE PARTIDA, NO UNA COPIA
                  </span>
                  <h2>
                    El método se comparte.
                    <br />
                    La memoria empieza de cero.
                  </h2>
                  <p>
                    Cada especialista nace con instrucciones revisables,
                    herramientas acotadas y un perfil Hermes independiente.
                  </p>
                  <div className="line-feature">
                    <ShieldCheck size={19} />
                    <div>
                      <h4>Alcance explícito</h4>
                      <p>
                        Lectura y escritura en su workspace del proyecto. Sin
                        terminal general.
                      </p>
                    </div>
                  </div>
                  <div className="line-feature">
                    <FileText size={19} />
                    <div>
                      <h4>Resultados que permanecen</h4>
                      <p>
                        Código, planes e imágenes reales, visibles desde el explorador y el chat.
                      </p>
                    </div>
                  </div>
                  <button
                    className="primary"
                    onClick={() =>
                      projects.length
                        ? openProject(projects[0])
                        : newModal(org ? "project" : "org")
                    }
                  >
                    Crear con Hapic <ArrowRight size={16} />
                  </button>
                </div>
              </div>
            ) : null}
            {page === "Herramientas" ? <ToolsPanel projects={projects} agents={state.agents} selectedProjectId={projectId} onSelectProject={setProjectId} /> : null}
            {page === "Configuración" ? (
              <div className="settings-layout">
                <section className="card settings-card">
                  <div className="card-title">
                    <Sparkles size={17} />
                    Modelo predeterminado
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      action(async () => {
                        await put("/settings/model", { model, effort });
                        await refresh();
                        setToast("Preferencias guardadas para agentes nuevos.");
                      });
                    }}
                  >
                    <p>
                      El punto de partida para Hapic y los nuevos agentes.
                      Puedes cambiarlo en cada conversación.
                    </p>
                    <label htmlFor="default-model">Modelo de OpenAI</label>
                    <ModelSelect
                      id="default-model"
                      value={model}
                      savedValue={state.settings.model}
                      onChange={setModel}
                      disabled={busy}
                    />
                    <label htmlFor="default-effort">
                      Esfuerzo de razonamiento
                    </label>
                    <select
                      id="default-effort"
                      value={effort}
                      onChange={(e) => setEffort(e.target.value)}
                    >
                      {["low", "medium", "high", "xhigh", "max"].map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                    <p className="field-help">
                      Se utiliza Responses API. Un esfuerzo mayor puede aumentar
                      el tiempo de respuesta y el consumo.
                    </p>
                    <button className="primary" disabled={busy}>
                      {busy ? (
                        <LoaderCircle size={15} className="spin" />
                      ) : (
                        <Check size={15} />
                      )}
                      Guardar preferencias
                    </button>
                  </form>
                </section>
                <section className="card settings-card">
                  <div className="card-title">
                    <ShieldCheck size={17} />
                    Conexión con OpenAI<span className="tag">Servidor</span>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const value = key;
                      setKey("");
                      action(async () => {
                        await put("/settings/openai", { api_key: value });
                        await refresh();
                        setToast(
                          "API key guardada. Inicia o reinicia los agentes para aplicarla.",
                        );
                      });
                    }}
                  >
                    <div className="setting-status">
                      <span
                        className={
                          "connection-dot " +
                          (caps?.openai.configured ? "ok" : "")
                        }
                      />
                      {caps?.openai.configured
                        ? "Credencial configurada"
                        : "API key pendiente"}
                    </div>
                    <p>
                      La clave se cifra en el servidor y nunca se devuelve al
                      navegador. El estado se guarda localmente; las consultas y
                      su contexto se envían a OpenAI.
                    </p>
                    <label htmlFor="openai-key">API key</label>
                    <input
                      id="openai-key"
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      placeholder={
                        caps?.openai.configured
                          ? "Introduce una nueva clave para reemplazarla"
                          : "sk-…"
                      }
                      disabled={caps?.openai.source === "environment"}
                      minLength={20}
                      required
                    />
                    <p className="field-help">
                      {caps?.openai.source === "environment"
                        ? "Administrada por la variable del servidor OPENAI_API_KEY."
                        : "No la pegues en una conversación. Usa solo este formulario local."}
                    </p>
                    <div className="button-row">
                      <button
                        className="primary"
                        disabled={
                          busy || !key || caps?.openai.source === "environment"
                        }
                      >
                        Guardar credencial
                      </button>
                      {caps?.openai.configured &&
                      caps.openai.source !== "environment" ? (
                        <button
                          className="text-button"
                          type="button"
                          onClick={() =>
                            action(async () => {
                              await api("/settings/openai", {
                                method: "DELETE",
                              });
                              await refresh();
                              setToast(
                                "Credencial eliminada del servidor. Los contenedores existentes conservan su entorno hasta reiniciarlos.",
                              );
                            })
                          }
                        >
                          Eliminar
                        </button>
                      ) : null}
                    </div>
                  </form>
                </section>
                <section className="card settings-card docker-card">
                  <div className="card-title">
                    <Box size={17} />
                    Runtime Docker
                    <button
                      className="icon-button"
                      aria-label="Comprobar Docker"
                      onClick={() => action(refresh)}
                    >
                      <RefreshCw size={15} />
                    </button>
                  </div>
                  <div className="settings-body">
                    <div className="setting-status">
                      <span
                        className={
                          "connection-dot " +
                          (caps?.docker.available ? "ok" : "")
                        }
                      />
                      {caps?.docker.available
                        ? "Motor conectado"
                        : "Motor no disponible"}
                    </div>
                    <p>{caps?.docker.message}</p>
                    <code>{caps?.docker.image}</code>
                    <p className="field-help">
                      Con Docker disponible y la credencial configurada, abre un
                      agente y pulsa Iniciar runtime. No se ha instalado
                      software del sistema automáticamente.
                    </p>
                  </div>
                </section>
                <div className="local-info">
                  <ShieldCheck size={18} />
                  <p>
                    <strong>Un MVP para uso local.</strong> Un operador
                    administra sus organizaciones y proyectos. El acceso
                    compartido y los roles empresariales quedan para una fase
                    posterior.
                  </p>
                </div>
              </div>
            ) : null}
          </>
        )}
        <footer className="page-footer">
          <span>
            <Mark small />
            Hapic
          </span>
          <span>El contexto permanece. El trabajo avanza.</span>
          <span>Local · MVP</span>
        </footer>
      </main>
      {toast ? (
        <div className="toast" role="status">
          <Check size={16} />
          {toast}
        </div>
      ) : null}
      {officeProject && state ? (
        <OfficeBoundary key={officeProject.id} close={closeOffice}>
          <Suspense fallback={<Modal title="Abriendo oficina 3D" close={closeOffice}><div className="loading"><LoaderCircle className="spin" size={22} /> Preparando la oficina de {officeProject.name}…</div></Modal>}>
            <ProjectOffice project={officeProject} agents={state.agents} execution={projectActivity} close={closeOffice} openAgent={openAgent} />
          </Suspense>
        </OfficeBoundary>
      ) : null}
      {createTemplate ? <CreateAgentModal template={createTemplate} projects={projects} agents={state?.agents || []} initialProjectId={projectId} close={() => setCreateTemplate(undefined)} created={async (created) => { await refresh(); setCreateTemplate(undefined); openAgent(created); setToast("Perfil creado. Consulta el estado real del runtime."); }} /> : null}
      {modal ? (
        <Modal
          title={
            modal === "org" ? "Crea tu espacio de trabajo" : "Un nuevo proyecto"
          }
          close={() => setModal(null)}
        >
          <form onSubmit={create}>
            <p className="muted">
              {modal === "org"
                ? "Una organización reúne tus proyectos y sus agentes."
                : "Hapic tendrá un perfil propio dentro de este proyecto."}
            </p>
            <label htmlFor="new-name">
              {modal === "org"
                ? "Nombre de la organización"
                : "Nombre del proyecto"}
            </label>
            <input
              autoFocus
              id="new-name"
              placeholder={
                modal === "org"
                  ? "Por ejemplo, Estudio Norte"
                  : "Por ejemplo, Mi nuevo producto"
              }
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              required
            />
            {modal === "org" ? (
              <>
                <label htmlFor="first-project">
                  Primer proyecto <span className="muted">(opcional)</span>
                </label>
                <input
                  id="first-project"
                  placeholder="Por ejemplo, Sitio web"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  maxLength={80}
                />
              </>
            ) : null}
            <div className="folder-preview">
              <Folder size={17} />
              <span>
                {modal === "org" ? name || "tu-organización" : org?.name}
                <ChevronRight size={13} />
                {modal === "org"
                  ? projectName || "proyectos"
                  : name || "tu-proyecto"}
                {modal !== "org" || projectName ? (
                  <>
                    <ChevronRight size={13} />
                    <Mark small />
                    Hapic
                  </>
                ) : null}
              </span>
            </div>
            <p className="field-help">
              Se crearán metadatos y carpetas reales. La conexión de IA se
              configura después.
            </p>
            {error ? (
              <p className="inline-error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="modal-actions">
              <button
                className="secondary"
                type="button"
                onClick={() => setModal(null)}
              >
                Cancelar
              </button>
              <button className="primary" disabled={busy || !name.trim()}>
                {busy ? <LoaderCircle className="spin" size={15} /> : null}Crear{" "}
                {modal === "org" ? "espacio" : "proyecto"}
                <ArrowRight size={15} />
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
function ProjectCard({
  project,
  count,
  click,
  office,
}: {
  project: Project;
  count: number;
  click: () => void;
  office: () => void;
}) {
  return (
    <article className="card project-card">
      <button className="project-card-open" onClick={click} aria-label={"Abrir proyecto " + project.name}>
      <div className="project-card-top">
        <span className="icon-tile">
          <Folder size={20} />
        </span>
        <ArrowUpRight size={16} className="muted" />
      </div>
      <h3>{project.name}</h3>
      <p>
        {count} {count === 1 ? "agente" : "agentes"} en este proyecto
      </p>
      </button>
      <button className="secondary project-office-button" onClick={office} aria-label={"Abrir oficina 3D de " + project.name}><Box size={15} /> Oficina 3D <ArrowUpRight size={14} /></button>
      <div className="project-card-footer">
        <code>{project.id.slice(0, 13)}</code>
        <span>
          {new Date(project.created_at).toLocaleDateString("es-CO", {
            day: "numeric",
            month: "short",
          })}
        </span>
      </div>
    </article>
  );
}
class OfficeBoundary extends React.Component<{ children: React.ReactNode; close: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <Modal title="No se pudo abrir la oficina" close={this.props.close}><div className="loading">Comprueba la conexión y recarga la página para volver a intentarlo.</div></Modal>;
    return this.props.children;
  }
}
function AgentTable({
  agents,
  projects,
  open,
  execution,
}: {
  agents: Agent[];
  projects: Project[];
  open: (a: Agent) => void;
  execution?: TeamExecution;
}) {
  const [query, setQuery] = useState("");
  const filtered = agents.filter(a => `${a.name} ${agentRoles[a.kind]} ${projects.find(p => p.id === a.project_id)?.name || ""}`.toLocaleLowerCase("es").includes(query.toLocaleLowerCase("es")));
  return agents.length ? (
    <section className="agents-table" aria-label="Directorio de agentes">
    <div className="team-table-toolbar"><label className="team-search"><Search size={16} /><input aria-label="Buscar agente, rol o proyecto" placeholder="Buscar por nombre o rol…" value={query} onChange={e => setQuery(e.target.value)} /></label><span className="tiny muted">{filtered.length} de {agents.length}</span></div>
    <div className="card table-scroll">
      <table>
        <thead>
          <tr>
            <th>Agente</th>
            <th>Proyecto</th>
            <th>Modelo</th>
            <th>Trabajo y estado</th>
            <th>
              <span className="sr-only">Abrir</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((a) => {
            const tasks = execution?.tasks?.filter(task => task.agent_id === a.id) || [];
            const task = tasks.find(task => task.executing) || tasks.find(task => task.state === "queued") || tasks[tasks.length - 1];
            return (
            <tr key={a.id} onClick={() => open(a)}>
              <td>
                <button
                  className="table-agent"
                  onClick={(e) => {
                    e.stopPropagation();
                    open(a);
                  }}
                >
                  <span className="agent-letter">
                    {a.kind === "hapic" ? "H" : a.name[0].toUpperCase()}
                  </span>
                  <span>
                    <strong>{a.name}</strong>
                    <small>
                      {agentRoles[a.kind]}
                    </small>
                    <small className="table-model-summary">{a.model} · {a.effort}</small>
                  </span>
                </button>
              </td>
              <td data-label="Proyecto">{projects.find((p) => p.id === a.project_id)?.name}</td>
              <td data-label="Modelo">
                <code>{a.model}</code>
                <small>{a.effort}</small>
              </td>
              <td>
                {task ? <div className="table-task"><span className={"team-task-status " + (task.executing ? "active" : task.state)}>{task.executing ? "En curso" : ({ queued: "En cola", delivered: "Entregada", completed: "Entregada", failed: "Fallida", blocked: "Bloqueada", running: "Sin ejecución confirmada" }[task.state] || task.state)}</span><span title={task.objective}>{task.objective}</span>{task.latest_activity && <small title={task.latest_activity}>{task.latest_activity}</small>}</div> : <div className="table-task">{a.kind === "hapic" && execution?.busy_agents?.includes(a.id) ? <span className="team-task-status active">Coordinando el equipo</span> : <span className="muted tiny">{execution ? "Sin tarea asignada" : "Abre el agente para ver su actividad"}</span>}</div>}
                <Badge status={a.status} />
              </td>
              <td>
                <button className="icon-button" aria-label={"Abrir conversación de " + a.name} onClick={e => { e.stopPropagation(); open(a); }}><ArrowUpRight size={16} /></button>
              </td>
            </tr>
          );})}
        </tbody>
      </table>
      {!filtered.length && <p className="team-no-results">No hay coincidencias. Prueba con otro nombre o rol.</p>}
    </div>
    </section>
  ) : (
    <Empty icon={<Sparkles size={27} />} title="Tu equipo empieza con Hapic">
      Crea un proyecto para preparar tu orquestador y sumar especialistas.
    </Empty>
  );
}
function RuntimeCard({ agent, runtime }: { agent: Agent; runtime: any }) {
  return (
    <section className="card runtime-card">
      <div className="card-title">
        <Box size={17} />
        Runtime real
      </div>
      <div className="runtime-body">
        <Badge status={runtime?.status || agent.status} />
        <div>
          <span className="muted tiny">CONTENEDOR</span>
          <code>{runtime?.container || "Sin contenedor comprobado"}</code>
        </div>
        <div>
          <span className="muted tiny">MODELO / RAZONAMIENTO</span>
          <code>{agent.model}</code>
          <span className="tag">{agent.effort}</span>
        </div>
        <div>
          <span className="muted tiny">ALMACENAMIENTO</span>
          <span className="storage-line">
            <Database size={15} />
            Perfil y workspace persistentes
          </span>
        </div>
        {agent.error ? <p className="runtime-error">{agent.error}</p> : null}
        <p className="tiny muted">
          El estado de la API se comprueba cada 6 segundos. Una API disponible
          no verifica el acceso al modelo hasta el primer turno.
        </p>
      </div>
    </section>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
