import { useEffect, useState, type FormEvent } from "react";
import { ExternalLink, Film, Link2, LoaderCircle, RefreshCw, Unplug } from "lucide-react";
import { api, post, videoUrl, type Agent, type Connection, type HeyGenVideo } from "./api";
import { VideoPreview } from "./components";

type Props = {
  projectId: string;
  agents: Agent[];
  connections: Connection[];
  busy: boolean;
  run: (work: () => Promise<void>) => Promise<void>;
  onChanged: (message: string) => Promise<void>;
};

const statuses: Record<HeyGenVideo["status"], string> = {
  submitting: "Enviando", submission_unknown: "Comprobar envío", pending: "En cola", processing: "Generando",
  completed: "Terminado", failed: "Falló", cancelled: "Cancelado",
};

export function HeyGenPanel({ projectId, agents, connections, busy, run, onChanged }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [videos, setVideos] = useState<HeyGenVideo[]>([]);
  const [loadError, setLoadError] = useState("");
  const [disconnectId, setDisconnectId] = useState("");

  useEffect(() => {
    let active = true;
    if (projectId) {
      api<{ videos: HeyGenVideo[] }>(`/projects/${projectId}/heygen/videos`)
        .then((result) => { if (active) setVideos(result.videos); })
        .catch((reason: Error) => { if (active) setLoadError(reason.message); });
    }
    return () => { active = false; };
  }, [projectId]);

  async function refreshVideos() {
    const result = await api<{ videos: HeyGenVideo[] }>(`/projects/${projectId}/heygen/videos`);
    setVideos(result.videos);
    setLoadError("");
  }

  function connect(event: FormEvent) {
    event.preventDefault();
    const key = apiKey.trim();
    setApiKey("");
    void run(async () => {
      const result = await post<{ account_name: string }>(`/projects/${projectId}/connections/heygen`, { api_key: key });
      await onChanged(`HeyGen conectado: ${result.account_name}. Revisa las asignaciones de los agentes; si ya estaban iniciados, reinicia su runtime para cargar las nuevas herramientas.`);
    });
  }

  return <section className="card tool-integration" aria-label="HeyGen">
    <div className="card-title"><Film size={20} /><strong>HeyGen</strong><span className="tag">Generación de vídeo</span></div>
    <div className="tool-body">
      <h2>De una idea a un clip con audio.</h2>
      <p>Genera vídeos de 5 a 15 segundos desde un texto o una imagen pública. El MP4 terminado se guarda en el workspace del agente y aparece en su conversación.</p>
      <div className="tool-features"><span>Texto a vídeo</span><span>Imagen a vídeo</span><span>Audio incluido</span><span>Reels y Shorts</span></div>
      <form className="heygen-key-form" onSubmit={connect}>
        <label htmlFor="heygen-api-key">API key de HeyGen para este proyecto</label>
        <input id="heygen-api-key" type="password" autoComplete="off" value={apiKey} minLength={20} maxLength={512} required disabled={busy || !projectId} onChange={(event) => setApiKey(event.target.value)} placeholder="Introduce tu API key" />
        <p className="field-help">La clave se verifica con HeyGen y se guarda cifrada en el servidor. El uso se cobra a tu saldo de API de HeyGen.</p>
        <div className="button-row">
          <button type="submit" className="primary" disabled={busy || !projectId || apiKey.trim().length < 20}>{busy ? <LoaderCircle size={16} className="spin" /> : <Link2 size={16} />}Conectar HeyGen</button>
          <a href="https://platform.heygen.com/api-keys" target="_blank" rel="noreferrer" className="text-button">Obtener API key <ExternalLink size={12} /></a>
        </div>
      </form>

      {!connections.length ? <div className="tool-empty">Conecta una cuenta y asígnala a tus agentes en Herramientas por agente.</div> : connections.map((connection) => <div key={connection.id} className="tool-connection">
        <div className="tool-channel-heading"><strong>{connection.account_name}</strong><span className={`tool-status ${connection.status === "connected" ? "connected" : ""}`}>{connection.status === "connected" ? "Cuenta verificada" : "Volver a conectar"}</span></div>
        <button className="text-button" type="button" disabled={busy} onClick={() => setDisconnectId(connection.id)}><Unplug size={13} />Desconectar</button>
        {disconnectId === connection.id ? <div className="tool-disconnect">
          <p>Se eliminará la clave de Hapic. Los trabajos ya enviados pueden seguir procesándose y facturarse en HeyGen; puedes revocar la clave desde su panel.</p>
          <div className="button-row"><button type="button" className="secondary" disabled={busy} onClick={() => setDisconnectId("")}>Cancelar</button><button type="button" className="primary" disabled={busy} onClick={() => { void run(async () => {
            await api(`/projects/${projectId}/connections/${connection.id}`, { method: "DELETE" });
            setDisconnectId("");
            await onChanged("HeyGen desconectado. La clave se eliminó de Hapic.");
          }); }}>Desconectar cuenta</button></div>
        </div> : null}
      </div>)}

      <p className="field-help">Por defecto: 5 segundos, 480p y formato vertical, aproximadamente US$0,05 por clip. Tarifas estimadas: 480p US$0,01/s · 768p US$0,018/s · 1080p US$0,04/s. El encuadre de una imagen de entrada se conserva.</p>
      <p>Pídele al agente asignado: «Genera un vídeo vertical de 5 segundos a 480p de una taza de café sobre una mesa, con sonido ambiente».</p>

      <div className="tool-connect-row heygen-jobs-heading"><h3>Vídeos del proyecto</h3><button type="button" className="secondary" disabled={busy || !projectId} onClick={() => { void run(refreshVideos); }}><RefreshCw size={14} />Actualizar lista</button></div>
      {loadError ? <p role="alert">{loadError}</p> : null}
      {!videos.length ? <p className="field-help">Los vídeos solicitados por los agentes aparecerán aquí.</p> : <div className="heygen-videos">{videos.map((video) => <article className="tool-connection" key={video.id}>
        <div className="tool-channel-heading"><strong>{agents.find((agent) => agent.id === video.agent_id)?.name || "Vídeo del proyecto"}</strong><span className={`tool-status ${video.saved ? "connected" : ""}`}>{video.saved ? "Guardado" : statuses[video.status]}</span></div>
        <p>{video.duration} s · {video.resolution} · {video.aspect_ratio} · Estimado US${video.estimated_cost_usd}</p>
        {video.error ? <p role="status">{video.error}</p> : null}
        {video.saved && video.path ? <VideoPreview src={videoUrl(projectId, video.path)} name={video.path.split("/").pop() || "Vídeo"} download={videoUrl(projectId, video.path, true)} /> : <button type="button" className="secondary" disabled={busy || ["failed", "cancelled", "submitting", "submission_unknown"].includes(video.status) || !connections.some((connection) => connection.id === video.connection_id && connection.status === "connected")} onClick={() => { void run(async () => {
          const result = await post<HeyGenVideo>(`/projects/${projectId}/heygen/videos/${video.id}/refresh`);
          setVideos((previous) => previous.map((item) => item.id === video.id ? result : item));
        }); }}><RefreshCw size={14} />Consultar y guardar</button>}
        {video.status === "submission_unknown" ? <p className="field-help">Retoma la solicitud original con tu agente para recuperar el envío, o comprueba su estado en HeyGen antes de pedir otra pieza.</p> : null}
      </article>)}</div>}
    </div>
  </section>;
}
