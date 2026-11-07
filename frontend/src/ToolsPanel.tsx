import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { Check, ExternalLink, Link2, LoaderCircle, RefreshCw, ShieldCheck, Unplug, Youtube } from "lucide-react";
import { api, post, put, agentRoles, type Agent, type Connection, type IntegrationTool, type Project, type ProjectTools, type ToolAssignment, type YouTubeSettings, type YouTubeVideos } from "./api";

type Props = {
  projects: Project[];
  agents: Agent[];
  selectedProjectId: string;
  onSelectProject: (id: string) => void;
};

function AssignmentForm({ agent, tool, binding, connections, busy, onSave }: {
  agent: Agent;
  tool: IntegrationTool;
  binding?: ToolAssignment;
  connections: Connection[];
  busy: boolean;
  onSave: (enabled: boolean, connectionId: string | null) => Promise<void>;
}) {
  const [enabled, setEnabled] = useState(Boolean(binding?.enabled));
  const [connectionId, setConnectionId] = useState(binding?.connection_id || "");
  const changed = enabled !== Boolean(binding?.enabled) || connectionId !== (binding?.connection_id || "");
  const labelId = `tool-${agent.id}-${tool.id}`;
  return <form className="tool-assignment" onSubmit={(event: FormEvent) => { event.preventDefault(); void onSave(enabled, connectionId || null); }}>
    <div className="tool-agent-name"><strong>{agent.name}</strong><span>{agentRoles[agent.kind]}</span></div>
    <label className="tool-toggle" htmlFor={labelId}>
      <input id={labelId} type="checkbox" checked={enabled} disabled={busy} onChange={(event) => setEnabled(event.target.checked)} />
      Habilitar {tool.name}
    </label>
    <label htmlFor={`${labelId}-connection`}>Canal para {agent.name}</label>
    <select id={`${labelId}-connection`} value={connectionId} disabled={busy || !enabled} onChange={(event) => setConnectionId(event.target.value)}>
      <option value="">Seleccionar canal</option>
      {connections.filter((item) => item.provider === tool.provider).map((item) => <option key={item.id} value={item.id}>{item.account_name}{item.status !== "connected" ? " · Reconectar" : ""}</option>)}
    </select>
    <div className="tool-assignment-footer">
      <span>{!enabled ? "Deshabilitada" : connectionId ? "Solo lectura" : "Pendiente de canal"}</span>
      <button className="secondary" disabled={busy || !changed} type="submit"><Check size={14} /> Guardar</button>
    </div>
  </form>;
}

export function ToolsPanel({ projects, agents, selectedProjectId, onSelectProject }: Props) {
  const [catalog, setCatalog] = useState<IntegrationTool[]>([]);
  const [settings, setSettings] = useState<YouTubeSettings>();
  const [snapshot, setSnapshot] = useState<{ projectId: string; data: ProjectTools }>();
  const [preview, setPreview] = useState<{ projectId: string; connectionId: string; data: YouTubeVideos }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disconnectId, setDisconnectId] = useState("");
  const projectId = projects.some((item) => item.id === selectedProjectId) ? selectedProjectId : projects[0]?.id || "";
  const data = snapshot?.projectId === projectId ? snapshot.data : undefined;
  const visiblePreview = preview?.projectId === projectId ? preview : undefined;
  const projectAgents = agents.filter((item) => item.project_id === projectId);

  useEffect(() => {
    let active = true;
    Promise.all([api<IntegrationTool[]>("/tools"), api<YouTubeSettings>("/settings/youtube")])
      .then(([tools, configuration]) => { if (active) { setCatalog(tools); setSettings(configuration); } })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setDisconnectId("");
    if (projectId) {
      api<ProjectTools>(`/projects/${projectId}/tools`)
        .then((result) => { if (active) setSnapshot({ projectId, data: result }); })
        .catch((reason: Error) => { if (active) setError(reason.message); });
    }
    return () => { active = false; };
  }, [projectId]);

  async function reloadProject(target: string) {
    const result = await api<ProjectTools>(`/projects/${target}/tools`);
    setSnapshot({ projectId: target, data: result });
  }

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try { await work(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo completar la operación."); }
    finally { setBusy(false); }
  }

  async function importCredentials(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    await run(async () => {
      if (file.size > 64_000) throw new Error("Selecciona el JSON de credenciales de Google Cloud, de hasta 64 KB.");
      let credentials: unknown;
      try { credentials = JSON.parse(await file.text()); }
      catch { throw new Error("El archivo no es un JSON válido. Descárgalo de nuevo desde Google Cloud."); }
      await put("/settings/youtube", { credentials });
      setSettings(await api<YouTubeSettings>("/settings/youtube"));
      setNotice("Credenciales de Google guardadas. Selecciona un proyecto y conecta su canal.");
    });
  }

  const connect = () => run(async () => {
    const result = await post<{ authorization_url: string }>(`/projects/${projectId}/connections/youtube/authorize`);
    const destination = new URL(result.authorization_url);
    if (destination.origin !== "https://accounts.google.com") throw new Error("No se pudo abrir la autorización de Google.");
    window.location.assign(destination.href);
  });

  return <div className="tools-page">
    {error ? <div className="error-banner" role="alert">{error}</div> : null}
    {notice ? <div className="tool-notice" role="status"><Check size={16} />{notice}</div> : null}
    <div className="tool-workspace">
      <div><label htmlFor="tools-project">Proyecto</label><p>Las conexiones y las asignaciones pertenecen a este proyecto.</p></div>
      <select id="tools-project" value={projectId} disabled={busy || !projects.length} onChange={(event) => { setError(""); setNotice(""); setPreview(undefined); onSelectProject(event.target.value); }}>
        {!projects.length ? <option value="">Crea primero un proyecto</option> : null}
        {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </div>

    <section className="card tool-integration">
      <div className="card-title"><Youtube size={20} /><strong>YouTube</strong><span className="tag">Solo lectura</span></div>
      <div className="tool-body">
        <h2>Tu canal, conectado a tu equipo.</h2>
        <p>Consulta vídeos, comentarios y rendimiento con cualquiera de tus agentes. Elige qué canal puede usar cada uno.</p>
        <div className="tool-features"><span>Canal</span><span>Vídeos</span><span>Comentarios</span><span>Métricas</span></div>

        {settings?.source === "file" ? <div className="tool-server-credentials">
          <div><ShieldCheck size={16} /><strong>Configuración administrada por el servidor</strong><span>{settings.configured ? "Disponible" : "Pendiente de revisión"}</span></div>
          <p>{settings.configured ? "Google está configurado para Hapic. Solo necesitas conectar y autorizar el canal de tu proyecto." : settings.message || "El administrador debe revisar las credenciales de Google del servidor."}</p>
        </div> : <details className="tool-credentials" open={!settings?.configured}>
          <summary><ShieldCheck size={16} />Google Cloud · Configuración del administrador<span>{settings?.configured ? "Configuradas" : "Pendientes"}</span></summary>
          <div>
            <p>Como operador de esta instalación local, puedes configurar aquí el cliente OAuth de Hapic. En Docker se puede montar como secreto del servidor; cada cliente solo autoriza su canal.</p>
            <label htmlFor="google-client-file">Archivo JSON de Google Cloud</label>
            <input id="google-client-file" type="file" accept=".json,application/json" disabled={busy || !settings} onChange={(event) => { void importCredentials(event); }} />
            <p className="field-help">La cuenta de cada cliente se autoriza por separado al conectar su canal.</p>
            <label>URI de redirección que debe figurar en Google Cloud</label>
            <code className="tool-redirect">{settings?.redirect_uri || "Cargando configuración…"}</code>
          </div>
        </details>}

        <div className="tool-connect-row">
          <div><h3>Canales del proyecto</h3><p>{!projects.length ? "Crea un proyecto para conectar su canal." : !settings?.configured ? "El administrador debe completar la configuración de Google para habilitar la conexión." : "Autoriza el canal con su cuenta propietaria de Google."}</p></div>
          <button type="button" className="primary" disabled={busy || !settings?.configured || !projectId} onClick={() => { void connect(); }}>
            {busy ? <LoaderCircle size={16} className="spin" /> : <Link2 size={16} />}Conectar YouTube
          </button>
        </div>
        {projectId && !data ? <p role="status">Cargando conexiones…</p> : null}
        {data && !data.connections.length ? <div className="tool-empty">Todavía no hay un canal conectado a este proyecto.</div> : null}
        {data?.connections.map((connection) => <div key={connection.id} className="tool-connection">
          <div className="tool-channel-heading">
            <div><strong>{connection.account_name}</strong><span className="tool-channel-id">{connection.account_id}</span></div>
            <span className={`tool-status ${connection.status === "connected" ? "connected" : ""}`}>{connection.status === "connected" ? "Conectado" : "Volver a autorizar"}</span>
          </div>
          <div className="button-row">
            <button type="button" className="secondary" disabled={busy || connection.status !== "connected"} onClick={() => { void run(async () => {
              const result = await api<YouTubeVideos>(`/projects/${projectId}/connections/${connection.id}/videos`);
              setPreview({ projectId, connectionId: connection.id, data: result });
            }); }}>Ver vídeos</button>
            {connection.status !== "connected" ? <button type="button" className="secondary" disabled={busy} onClick={() => { void connect(); }}><RefreshCw size={14} />Reconectar</button> : null}
            <a href={`https://studio.youtube.com/channel/${connection.account_id}`} target="_blank" rel="noreferrer" className="text-button">YouTube Studio <ExternalLink size={12} /></a>
            <button type="button" className="text-button" disabled={busy} onClick={() => setDisconnectId(connection.id)}><Unplug size={13} />Desconectar</button>
          </div>
          {disconnectId === connection.id ? <div className="tool-disconnect" role="group" aria-label={`Desconectar ${connection.account_name}`}>
            <p>Se revocará el acceso en Google y los agentes dejarán de usar este canal. Google también puede invalidar otras conexiones de Hapic autorizadas con la misma cuenta.</p>
            <div className="button-row"><button type="button" className="secondary" disabled={busy} onClick={() => setDisconnectId("")}>Cancelar</button><button type="button" className="primary" disabled={busy} onClick={() => { void run(async () => {
              await api(`/projects/${projectId}/connections/${connection.id}`, { method: "DELETE" });
              setDisconnectId(""); setPreview(undefined); await reloadProject(projectId);
              setNotice("Canal desconectado y credenciales eliminadas de este equipo.");
            }); }}>Desconectar canal</button></div>
          </div> : null}
        </div>)}
        <p className="field-help">Si la aplicación de Google está en modo de prueba, necesitarás volver a autorizar después de siete días.</p>
      </div>
    </section>

    {visiblePreview ? <section className="card tool-videos" aria-label="Vídeos de YouTube">
      <div className="card-title"><Youtube size={17} />Vídeos del canal<span className="muted">Consulta real</span></div>
      <div className="tool-body">
        {!visiblePreview.data.videos.length ? <p>No hay vídeos disponibles en esta página.</p> : <div className="table-scroll"><table><thead><tr><th>Vídeo</th><th>Visibilidad</th><th>Visualizaciones</th></tr></thead><tbody>
          {visiblePreview.data.videos.map((video) => <tr key={video.id}><td><a href={`https://www.youtube.com/watch?v=${video.id}`} target="_blank" rel="noreferrer">{video.title} <ExternalLink size={12} /></a></td><td>{{ private: "Privado", public: "Público", unlisted: "Oculto" }[video.privacy_status] || video.privacy_status}</td><td>{video.statistics.viewCount !== undefined ? Number(video.statistics.viewCount).toLocaleString("es") : "No disponible"}</td></tr>)}
        </tbody></table></div>}
        <div className="tool-preview-footer"><span>Consultado: {new Date(visiblePreview.data.fetched_at).toLocaleString("es")}</span>
          {visiblePreview.data.next_page_token ? <button type="button" className="secondary" disabled={busy} onClick={() => { void run(async () => {
            const result = await api<YouTubeVideos>(`/projects/${projectId}/connections/${visiblePreview.connectionId}/videos?page_token=${encodeURIComponent(visiblePreview.data.next_page_token || "")}`);
            setPreview({ projectId, connectionId: visiblePreview.connectionId, data: result });
          }); }}>Página siguiente</button> : null}
        </div>
      </div>
    </section> : null}

    <section className="card tool-agent-section">
      <div className="card-title"><ShieldCheck size={17} />Herramientas por agente</div>
      <div className="tool-body">
        <p>Todos los agentes pueden integrar las herramientas del catálogo. Community Manager incluye YouTube preseleccionado; asigna un canal para que pueda consultarlo.</p>
        {!projectAgents.length ? <div className="tool-empty">Los agentes de tu proyecto aparecerán aquí.</div> : !data || !catalog.length ? <p role="status">Cargando asignaciones…</p> : <div className="tool-assignment-grid">
          {projectAgents.flatMap((agent) => catalog.map((tool) => {
            const binding = data.assignments.find((item) => item.agent_id === agent.id && item.tool_id === tool.id);
            return <AssignmentForm key={`${agent.id}:${tool.id}:${binding?.enabled || 0}:${binding?.connection_id || ""}`} agent={agent} tool={tool} binding={binding} connections={data.connections} busy={busy} onSave={(enabled, connectionId) => run(async () => {
              const result = await put<{ runtime_restart_required: boolean }>(`/agents/${agent.id}/tools/${tool.id}`, { enabled, connection_id: connectionId });
              await reloadProject(projectId);
              setNotice(result.runtime_restart_required ? "Asignación guardada. Reinicia el runtime del agente para actualizar su lista de herramientas." : "Asignación guardada. Se aplicará al iniciar el agente.");
            })} />;
          }))}
        </div>}
      </div>
    </section>
  </div>;
}
