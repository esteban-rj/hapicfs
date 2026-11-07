import { useEffect, useState } from "react";
import { api, type Agent, type Attachment } from "./api";
import { FileText, Download, Image, Film } from "lucide-react";

type Artifact = Attachment & { agent_id: string | null; agent_name: string; media_type: string; size: number; download_url: string };

export function ArtifactsPanel({ agent, version }: { agent: Agent; version: number }) {
  const [files, setFiles] = useState<Artifact[]>([]);
  const [selected, setSelected] = useState<Artifact>();
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ files: Artifact[] }>(`/projects/${agent.project_id}/artifacts`).then((result) => {
      if (active) { setFiles(result.files.filter((file) => agent.kind === "hapic" || file.agent_id === agent.id)); setError(""); }
    }).catch(() => { if (active) setError("No se pudieron consultar los entregables."); });
    return () => { active = false; };
  }, [agent.id, agent.project_id, agent.kind, version]);
  useEffect(() => {
    let active = true;
    setContent("");
    if (selected?.media_type === "text") fetch(selected.url).then(async (response) => {
      if (!response.ok) throw new Error();
      const text = await response.text();
      if (active) setContent(text);
    }).catch(() => { if (active) setContent("No se pudo abrir el archivo."); });
    return () => { active = false; };
  }, [selected]);
  return <details className="artifacts-panel">
    <summary><FileText size={16} /> Entregables {agent.kind === "hapic" ? "del proyecto" : `de ${agent.name}`} · {files.length} archivos</summary>
    <p>Guardados en este PC, en el workspace de cada agente. No se publican automáticamente en Internet.</p>
    {error ? <p role="alert">{error}</p> : null}
    {!files.length && !error ? <p>Aún no se encontraron archivos entregables. Un guion o brief no equivale a una imagen o un vídeo generado.</p> : null}
    <div className="artifacts-list">{files.map((file) => <div key={file.path}>
      <button type="button" className="text-button" onClick={() => setSelected(file)}>{file.media_type === "image" ? <Image size={16} /> : file.media_type === "video" ? <Film size={16} /> : <FileText size={16} />} {file.name}</button>
      <span>{file.agent_name} · {Math.ceil(file.size / 1024)} KB</span>
      <a href={file.download_url} download><Download size={14} /> Descargar</a>
      <small>{file.path}</small>
    </div>)}</div>
    {selected ? <section className="artifact-reader"><strong>{selected.agent_name} · {selected.name}</strong><a href={selected.url} target="_blank" rel="noreferrer">Abrir en otra pestaña</a>
      {selected.media_type === "image" ? <img src={selected.url} alt={selected.name} /> : selected.media_type === "video" ? <video src={selected.url} controls preload="metadata" /> : <pre>{content || "Cargando…"}</pre>}
    </section> : null}
  </details>;
}
