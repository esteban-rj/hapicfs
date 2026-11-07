import { useEffect, useRef, useState, type ReactNode } from "react";
import { ModelSelect } from "./ModelSelect";
import { ArtifactsPanel } from "./ArtifactsPanel";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  X,
  ArrowUp,
  LoaderCircle,
  Sparkles,
  Copy,
  Check,
  LockKeyhole,
  Image as ImageIcon,
} from "lucide-react";
import {
  api,
  post,
  put,
  agentRoles,
  imageUrl,
  videoUrl,
  type Agent,
  type Message,
  type Attachment,
  type Project,
  type FileNode,
  type Template,
} from "./api";

export function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={"mark " + (small ? "small" : "")} aria-hidden="true">
      H
    </span>
  );
}
export function Badge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    pending: "Pendiente de iniciar",
    provisioning: "Preparando runtime",
    running: "API disponible",
    blocked: "Requiere configuración",
    error: "Error de provisión",
    stopped: "Detenido",
    unavailable: "Sin conexión",
    starting: "API iniciando",
  };
  return (
    <span className={"status " + status}>
      <i />
      {labels[status] || status}
    </span>
  );
}
export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    dialog?.querySelector("input")?.focus();
    return () => {
      dialog?.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={close}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button className="icon-button" aria-label="Cerrar" onClick={close}>
          <X size={19} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function Tree({
  node,
  select,
  selected,
  label,
  depth = 0,
}: {
  node: FileNode;
  select: (n: FileNode) => void;
  selected?: string;
  label?: string;
  depth?: number;
}) {
  const [open, setOpen] = useState(depth < 4);
  const directory = node.type === "directory";
  return (
    <div>
      <button
        className={"tree-node " + (node.path === selected ? "selected" : "")}
        style={{ paddingLeft: 12 + depth * 14 }}
        onClick={() => (directory ? setOpen(!open) : select(node))}
        title={node.path}
        disabled={!directory && !node.preview}
      >
        {directory ? (
          open ? (
            <ChevronDown size={13} />
          ) : (
            <ChevronRight size={13} />
          )
        ) : (
          <span className="tree-spacer" />
        )}
        {directory ? (
          <Folder size={15} />
        ) : node.preview ? (
          node.media_type === "image" ? <ImageIcon size={15} /> : <FileText size={15} />
        ) : (
          <LockKeyhole size={14} />
        )}
        <span>{label || node.name}</span>
      </button>
      {directory && open
        ? node.children?.map((child) => (
            <Tree
              key={child.path}
              node={child}
              select={select}
              selected={selected}
              depth={depth + 1}
            />
          ))
        : null}
    </div>
  );
}
export function TemplateCard({
  template,
  compact = false,
  onUse,
}: {
  template: Template;
  compact?: boolean;
  onUse?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <section className="card template-card">
      <div className="card-heading">
        <span className="icon-tile">
          <Sparkles size={20} />
        </span>
        <div>
          <h3>{template.name}</h3>
          <span className="muted tiny">Plantilla · v{template.version}</span>
        </div>
        <span className="tag">{template.role}</span>
      </div>
      <p>{template.description}</p>
      <div className="capability-list">
        {template.capabilities.map((item, i) => (
          <div key={item}>
            <span className="step-number">0{i + 1}</span>
            {item}
          </div>
        ))}
      </div>
      {!compact ? (
        <>
          <h4>Antes de empezar</h4>
          <ul className="questions">
            {template.questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
          <div className="evidence">
            <strong>Forma de trabajo</strong>
            <p>{template.evidence_policy}</p>
          </div>
          {template.recommended_model ? <p className="model-recommendation"><strong>Modelo recomendado</strong><br /><code>{template.recommended_model}</code> · {template.recommended_effort}<br />{template.model_guidance}</p> : null}
          <h4>Entregables</h4>
          <div className="file-tags">
            {template.deliverables.map((d) => (
              <code key={d}>{d}</code>
            ))}
          </div>
          <button
            className="secondary"
            onClick={async () => {
              await navigator.clipboard.writeText(template.instructions);
              setCopied(true);
            }}
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
            {copied ? "Instrucciones copiadas" : "Copiar instrucciones"}
          </button>
        </>
      ) : (
        <p className="tiny muted">
          Memoria nueva y herramientas limitadas a su workspace.
        </p>
      )}
      {onUse ? <button className="primary template-use" onClick={onUse}>Usar plantilla <ChevronRight size={15} /></button> : null}
    </section>
  );
}

export function ImagePreview({ src, alt, download }: { src: string; alt: string; download: string }) {
  const [failed, setFailed] = useState(false);
  return <figure className="image-preview">
    {failed ? <p role="alert">No se pudo cargar esta imagen. Comprueba que el archivo siga en el workspace.</p> : <a href={src} target="_blank" rel="noreferrer"><img src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} /></a>}
    <figcaption><span>{alt}</span><a href={download} download>Descargar</a></figcaption>
  </figure>;
}

export function VideoPreview({ src, name, download }: { src: string; name: string; download: string }) {
  const [failed, setFailed] = useState(false);
  return <figure className="image-preview video-preview">
    {failed ? <p role="alert">No se pudo cargar el vídeo. Comprueba que el archivo siga en el workspace.</p> : <video controls preload="metadata" src={src} aria-label={name} onError={() => setFailed(true)} />}
    <figcaption><span>{name}</span><a href={download} download>Descargar MP4</a></figcaption>
  </figure>;
}

function MessageContent({ message, agent }: { message: Message; agent: Agent }) {
  // Render local workspace image references only; no HTML or arbitrary remote requests.
  const pieces = message.content.split(/(!\[[^\]]*\]\([^)]+\))/g);
  return <>
    {pieces.map((piece, index) => {
      const match = piece.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
      if (!match) return piece ? <p key={index}>{piece.split(/(https?:\/\/(?:127\.0\.0\.1|localhost):\d+(?:\/[^\s<>]*)?|\/api\/agents\/agt_[A-Za-z0-9]+\/preview\/open)/g).map((part, position) => /^(?:https?:\/\/(?:127\.0\.0\.1|localhost):\d+|\/api\/agents\/agt_[A-Za-z0-9]+\/preview\/open$)/.test(part) ? <a key={position} href={part.replace(/[.,;)]+$/, "")} target="_blank" rel="noreferrer">{part.startsWith("/api/") ? "Abrir vista previa" : part}</a> : part)}</p> : null;
      const raw = match[2].replace(/^<|>$/g, "");
      if (/^(?:https?:|data:|javascript:|\/\/)/i.test(raw)) return <p key={index}>{match[1] || "Referencia de imagen externa"}</p>;
      const relative = raw.replace(/^\/workspace\//, "").replace(/^\.\//, "");
      const path = relative.startsWith("agents/") || relative.startsWith("workspace/") ? relative : `agents/${agent.id}/workspace/${relative}`;
      return <ImagePreview key={path} src={imageUrl(agent.project_id, path)} alt={match[1] || relative} download={imageUrl(agent.project_id, path, true)} />;
    })}
    {message.attachments?.map((item) => item.mime_type === "video/mp4" ? <VideoPreview key={item.id} src={videoUrl(agent.project_id, item.path)} name={item.name} download={videoUrl(agent.project_id, item.path, true)} /> : item.mime_type.startsWith("image/") ? <ImagePreview key={item.id} src={imageUrl(agent.project_id, item.path)} alt={item.name} download={imageUrl(agent.project_id, item.path, true)} /> : <div className="document-attachment" key={item.id}><FileText size={17} /><strong>{item.name}</strong><a href={item.url} target="_blank" rel="noreferrer">Abrir documento</a><a href={item.url + "&download=true"} download>Descargar</a><small>{item.path}</small></div>)}
  </>;
}

export function CreateAgentModal({ template, projects, agents, initialProjectId, close, created }: { template: Template; projects: Project[]; agents: Agent[]; initialProjectId: string; close: () => void; created: (agent: Agent) => Promise<void> }) {
  const [projectId, setProjectId] = useState(initialProjectId || projects[0]?.id || "");
  const [name, setName] = useState("");
  const [plannerId, setPlannerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const planners = agents.filter((a) => a.project_id === projectId && a.kind === "architect");
  const selectedPlanner = planners.find((a) => a.id === plannerId)?.id || (planners.length === 1 ? planners[0].id : "");
  return <Modal title={"Crear · " + template.name} close={() => { if (!busy) close(); }}>
    <form onSubmit={async (event) => {
      event.preventDefault();
      setBusy(true); setError("");
      try { const agent = await post<Agent>(`/projects/${projectId}/agents`, { name, template: template.kind, planner_id: template.kind === "coder" ? selectedPlanner : null }); await created(agent); }
      catch (error) { setError((error as Error).message); }
      finally { setBusy(false); }
    }}>
      <p className="muted">{template.description} El perfil tendrá memoria nueva y archivos persistentes.</p>
      <label htmlFor="agent-project">Proyecto</label>
      <select id="agent-project" value={projectId} required disabled={busy} onChange={(e) => { setProjectId(e.target.value); setPlannerId(""); }}><option value="">Selecciona un proyecto</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <label htmlFor="agent-name">Nombre del agente</label>
      <input id="agent-name" value={name} maxLength={80} required disabled={busy} onChange={(e) => setName(e.target.value)} placeholder="Elige su nombre" />
      {template.kind === "coder" ? <><label htmlFor="agent-planner">Arquitecto / Planner</label><select id="agent-planner" value={selectedPlanner} onChange={(e) => setPlannerId(e.target.value)} required disabled={busy}><option value="">Selecciona un arquitecto</option>{planners.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select><p className="field-help">{planners.length ? "El coder leerá el plan publicado por este arquitecto antes de escribir código." : "Primero crea un arquitecto/planner en este proyecto."}</p></> : null}
      {template.recommended_model ? <p className="field-help">Recomendación: {template.recommended_model} · {template.recommended_effort}. Se aplicarán tus preferencias globales, ajustables en el chat. {template.model_guidance}</p> : null}
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      <div className="modal-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>Cancelar</button><button className="primary" disabled={busy || !projectId || (template.kind === "coder" && !selectedPlanner)}>{busy ? "Preparando…" : "Crear agente"}</button></div>
    </form>
  </Modal>;
}

export function Chat({
  agent,
  connected,
  changed,
  onSettings,
  onPrepare,
  templates,
}: {
  agent: Agent;
  connected: boolean;
  changed: () => Promise<void>;
  onSettings: () => void;
  onPrepare: (kind: Template["kind"]) => void;
  templates: Template[];
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const imageInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [execution, setExecution] = useState<{
    busy: boolean; provisioning: boolean; active_tasks: number; queued_tasks: number;
    run: { state: string; started_at: string; updated_at: string } | null;
    tasks: { id: string; agent_name: string; objective: string; state: string; executing: boolean; updated_at: string; result: string | null; latest_activity?: string; activity_at?: string }[];
  }>();
  const [executionError, setExecutionError] = useState("");
  const working = busy || !!execution?.busy;
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const [model, setModel] = useState(agent.model);
  const [effort, setEffort] = useState(agent.effort);
  useEffect(() => { setAttachments([]); setText(""); setExecution(undefined); }, [agent.id]);
  async function attachImages(files: FileList | null) {
    if (!files?.length) return;
    if (files.length + attachments.length > 3) { setError("Adjunta como máximo tres imágenes."); return; }
    setUploading(true);
    setError("");
    try {
      for (const file of Array.from(files)) {
        if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 8 * 1024 * 1024)
          throw new Error("Usa imágenes PNG, JPEG o WebP de hasta 8 MB.");
        const attachment = await api<Attachment>(`/agents/${agent.id}/images`, {
          method: "POST", headers: { "Content-Type": file.type }, body: file,
        });
        setAttachments((items) => [...items, attachment]);
      }
    } catch (e) { setError((e as Error).message); }
    finally { setUploading(false); if (imageInput.current) imageInput.current.value = ""; }
  }
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [status, saved] = await Promise.all([
          api<NonNullable<typeof execution>>(`/agents/${agent.id}/execution`),
          api<Message[]>(`/agents/${agent.id}/messages`),
        ]);
        if (active) {
          setExecution(status);
          setExecutionError("");
          if (status.busy) setError("");
          if (!busy) setMessages((previous) => JSON.stringify(previous) === JSON.stringify(saved) ? previous : saved);
        }
      } catch {
        if (active) setExecutionError("No se pudo actualizar el estado. Comprobando de nuevo…");
      }
      if (active) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [agent.id, busy]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, busy]);
  async function send(e: React.FormEvent) {
    e.preventDefault();
    if ((!text.trim() && !attachments.length) || working || uploading || !execution || executionError) return;
    const draft = text;
    const sentAttachments = attachments;
    const input = text.trim() || "Describe y analiza las imágenes adjuntas.";
    setBusy(true);
    setError("");
    try {
      if (model !== agent.model || effort !== agent.effort)
        await put("/agents/" + agent.id + "/model", { model, effort });
      setText("");
      setAttachments([]);
      setMessages((m) => [
        ...m,
        { id: -Date.now(), role: "user", content: input, source: "user", attachments },
      ]);
      await post("/agents/" + agent.id + "/chat", {
        content: input,
        request_id: crypto.randomUUID(),
        image_ids: attachments.map((item) => item.id),
      });
      setMessages(await api("/agents/" + agent.id + "/messages"));
      await changed();
    } catch (e) {
      setError((e as Error).message);
      const saved = await api<Message[]>("/agents/" + agent.id + "/messages").catch(() => null);
      if (saved) {
        setMessages(saved);
        const received = saved.some((message) => message.role === "user" && message.content === input && !messages.some((previous) => previous.id === message.id));
        if (!received) {
          setText(draft);
          setAttachments(sentAttachments);
        }
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="chat-shell">
      <div className="chat-heading">
        <Mark small />
        <div>
          <strong>{agent.name}</strong>
          <span className="tiny muted">
            {agentRoles[agent.kind]}
          </span>
        </div>
        <span className="tag">Hermes</span>
      </div>
      <div className="execution-status" role="status" aria-live="polite">
        {working || !!execution?.active_tasks ? <LoaderCircle className="spin" size={16} /> : null}
        <strong>{executionError || (!execution ? "Consultando estado…" : working ? (execution.provisioning ? "Preparando runtime…" : `${agent.name} está trabajando…`) : execution.active_tasks ? "El equipo está ejecutando tareas…" : execution.queued_tasks ? "Hay tareas en cola, esperando su turno o dependencias…" : "Sin ejecución activa")}</strong>
        {execution?.run && working ? <span>Desde {new Date(execution.run.started_at).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}</span> : null}
        {execution?.run?.state === "interrupted" && !working ? <span>El turno anterior se interrumpió al reiniciar el servidor. Revisa sus avances antes de repetirlo.</span> : null}
        {execution?.run?.state === "failed" && !working ? <span>El último turno terminó con un error. Revisa la actividad y las tareas.</span> : null}
      </div>
      {execution?.tasks.length ? <details className="execution-tasks" open={working || execution.active_tasks > 0 || execution.queued_tasks > 0}>
        <summary>Tareas del {agent.kind === "hapic" ? "equipo" : "agente"}: {execution.active_tasks} en ejecución · {execution.queued_tasks} en cola · {execution.tasks.filter((task) => task.state === "delivered").length} entregadas · {execution.tasks.filter((task) => task.state === "failed").length} fallidas</summary>
        <ul>{execution.tasks.map((task) => <li key={task.id}>
          <strong>{task.agent_name}</strong>
          <span className={`task-state task-${task.state}`}>{task.state === "running" ? task.executing ? "En ejecución" : "Requiere revisión: ejecución sin confirmar" : (({ queued: "En cola · espera turno o dependencias", planned: "Asignada", blocked: "Bloqueada", failed: "Fallida", delivered: "Entregada · pendiente de validación" } as Record<string, string>)[task.state] || task.state)}</span>
          <p>{task.objective}</p>
          <small>{task.id} · Límite: 10 minutos</small>
          {task.latest_activity ? <p>Última actividad: {task.latest_activity}</p> : null}
          <small>Actualizada: {new Date(task.updated_at).toLocaleTimeString("es")}</small>
          {task.state === "failed" || task.state === "blocked" ? <p>{task.result}</p> : null}
        </li>)}</ul>
      </details> : agent.kind === "hapic" && execution ? <p className="execution-empty">Todavía no hay tareas asignadas al equipo.</p> : null}
      <div className="messages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <span className="welcome-symbol">
              {agent.kind === "hapic" ? <Mark /> : <Sparkles size={30} />}
            </span>
            <h2>
              {agent.kind === "hapic"
                ? "¿Qué vamos a crear?"
                : agentRoles[agent.kind]}
            </h2>
            <p>
              {agent.kind === "hapic"
                ? "Dale a tu proyecto un especialista con contexto, memoria y un espacio propio."
                : templates.find((t) => t.kind === agent.kind)?.description}
            </p>
            {agent.kind === "hapic" ? (
              <div className="template-choices">{templates.map((template) => <button
                key={template.kind}
                className="secondary"
                disabled={busy}
                onClick={() => {
                  if (connected)
                    setText(`Quiero crear un ${template.name} para este proyecto.`);
                  else onPrepare(template.kind);
                }}
              >
                <Sparkles size={16} />
                {connected ? "Crear " : "Preparar "}{template.name}
              </button>)}</div>
            ) : null}
            {!connected ? (
              <div className="offline-note">
                <span className="status">
                  <i />
                  IA pendiente de conexión
                </span>
                <p>
                  Puedes preparar perfiles y archivos. Para conversar, configura
                  OpenAI e inicia el runtime Docker.
                </p>
                <button className="text-button" onClick={onSettings}>
                  Ir a configuración <ChevronRight size={14} />
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
        {messages.map((m) => (
          <div className={"message " + m.role} key={m.id}>
            {m.role !== "user" ? <Mark small /> : null}
            <div className="message-body">
              <span className="message-label">
                {m.role === "user" ? "Tú" : agent.name + (m.source === "artifact" ? " · Archivo guardado" : m.source === "task-update" ? " · Actividad del equipo" : " · Hermes")}
              </span>
              <MessageContent message={m} agent={agent} />
            </div>
          </div>
        ))}
        {working ? (
          <div className="thinking">
            <LoaderCircle className="spin" size={16} />
            Hermes está trabajando…
          </div>
        ) : null}
        <div ref={bottom} />
      </div>
      {error ? (
        <div className="inline-error" role="alert">
          {error}
        </div>
      ) : null}
      <ArtifactsPanel agent={agent} version={messages.length} />
      <form className="composer" onSubmit={send}>
        <input ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={(e) => void attachImages(e.target.files)} />
        {attachments.length ? <div className="pending-images">
          {attachments.map((item) => <div key={item.id}>
            <img src={item.url} alt="Imagen adjunta pendiente de enviar" />
            <button type="button" disabled={busy || uploading} aria-label="Quitar imagen" onClick={() => setAttachments((items) => items.filter((image) => image.id !== item.id))}><X size={14} /></button>
          </div>)}
        </div> : null}
        <label className="sr-only" htmlFor="chat-input">
          Mensaje para {agent.name}
        </label>
        <textarea
          id="chat-input"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            "Escribe a " + agent.name + "…"
          }
          disabled={working || !connected}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="composer-bottom">
          <div className="composer-selects">
            <button type="button" className="text-button" disabled={working || uploading || !connected || attachments.length >= 3} onClick={() => imageInput.current?.click()} title="PNG, JPEG o WebP · hasta 8 MB por imagen">
              <ImageIcon size={17} /> {uploading ? "Subiendo…" : "Adjuntar imagen"}
            </button>
            <label>
              <span className="sr-only">Modelo de la conversación</span>
              <ModelSelect
                value={model}
                savedValue={agent.model}
                onChange={setModel}
                ariaLabel="Modelo de la conversación"
                disabled={busy}
              />
            </label>
            <label>
              <span className="sr-only">Razonamiento</span>
              <select
                value={effort}
                onChange={(e) => setEffort(e.target.value)}
                aria-label="Razonamiento de la conversación"
                disabled={busy}
              >
                {["low", "medium", "high", "xhigh", "max"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          </div>
          <button
            className="send"
            aria-label="Enviar mensaje"
            disabled={working || uploading || !execution || !!executionError || (!text.trim() && !attachments.length) || !connected}
          >
            {busy ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <ArrowUp size={18} />
            )}
          </button>
        </div>
      </form>
      <p className="chat-footnote">
        Estado y memoria locales. Las consultas y el contexto se envían a
        OpenAI.
      </p>
    </section>
  );
}
