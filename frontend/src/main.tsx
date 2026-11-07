import React, { useCallback, useEffect, useState } from "react";
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
  Database,
  FileText,
  Folder,
  FolderPlus,
  LayoutGrid,
  Layers,
  LoaderCircle,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
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
} from "./components";
import "./style.css";
import { ModelSelect } from "./ModelSelect";
import { ToolsPanel } from "./ToolsPanel";

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
  const [agentId, setAgentId] = useState("");
  const [page, setPage] = useState<Page>("Resumen");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [modal, setModal] = useState<"org" | "project" | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [tree, setTree] = useState<FileNode>();
  const [file, setFile] = useState<{
    path: string;
    content: string;
    size: number;
    media_type?: "image" | "text";
  }>();
  const [runtime, setRuntime] = useState<any>();
  const [events, setEvents] = useState<any[]>([]);
  const [tab, setTab] = useState<"Conversación" | "Archivos" | "Actividad">(
    "Conversación",
  );
  const [model, setModel] = useState("gpt-6.1-sol");
  const [effort, setEffort] = useState("xhigh");
  const [key, setKey] = useState("");
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
  const agents =
    state?.agents.filter(
      (a) =>
        a.organization_id === orgId &&
        (!projectId || a.project_id === projectId),
    ) || [];
  const agent = agents.find((a) => a.id === agentId);
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
    setProjectId(a.project_id);
    setAgentId(a.id);
    setPage("Agentes");
    setTab("Conversación");
    setFile(undefined);
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
    if (n.media_type === "image") {
      setFile({ path: n.path, content: "", size: n.size || 0, media_type: "image" });
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
  return (
    <>
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
          {projects.length ? (
            projects.map((p) => (
              <div key={p.id}>
                <button
                  className={
                    "project-nav " + (projectId === p.id ? "current" : "")
                  }
                  onClick={() => openProject(p)}
                >
                  <Folder size={15} />
                  <span>{p.name}</span>
                </button>
                {projectId === p.id
                  ? state?.agents
                      .filter((a) => a.project_id === p.id)
                      .map((a) => (
                        <button
                          className={
                            "agent-nav " + (a.id === agentId ? "current" : "")
                          }
                          key={a.id}
                          onClick={() => openAgent(a)}
                        >
                          <span>
                            {a.kind === "hapic" ? "H" : a.name[0].toUpperCase()}
                          </span>
                          {a.name}
                        </button>
                      ))
                  : null}
              </div>
            ))
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
                          file.media_type === "image" ? <ImagePreview key={file.path} src={imageUrl(projectId, file.path)} alt={file.path.split("/").pop() || "Imagen del proyecto"} download={imageUrl(projectId, file.path, true)} /> : <pre>{file.content}</pre>
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
                <AgentTable
                  agents={agents}
                  projects={projects}
                  open={openAgent}
                />
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
    </>
  );
}
function ProjectCard({
  project,
  count,
  click,
}: {
  project: Project;
  count: number;
  click: () => void;
}) {
  return (
    <button className="card project-card" onClick={click}>
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
      <div className="project-card-footer">
        <code>{project.id.slice(0, 13)}</code>
        <span>
          {new Date(project.created_at).toLocaleDateString("es-CO", {
            day: "numeric",
            month: "short",
          })}
        </span>
      </div>
    </button>
  );
}
function AgentTable({
  agents,
  projects,
  open,
}: {
  agents: Agent[];
  projects: Project[];
  open: (a: Agent) => void;
}) {
  return agents.length ? (
    <div className="card table-scroll">
      <table>
        <thead>
          <tr>
            <th>Agente</th>
            <th>Proyecto</th>
            <th>Modelo</th>
            <th>Estado registrado</th>
            <th>
              <span className="sr-only">Abrir</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
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
                  </span>
                </button>
              </td>
              <td>{projects.find((p) => p.id === a.project_id)?.name}</td>
              <td>
                <code>{a.model}</code>
                <small>{a.effort}</small>
              </td>
              <td>
                <Badge status={a.status} />
              </td>
              <td>
                <ChevronRight size={15} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
