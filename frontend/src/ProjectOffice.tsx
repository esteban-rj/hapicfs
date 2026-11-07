import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Box, Focus, Maximize2, MessageCircle, Minus, Plus, RotateCcw, X } from "lucide-react";
import { agentRoles, type Agent, type Project } from "./api";
import { officeColors, officeMembers, officePresence, type OfficeExecution } from "./officeModel";
import { createProjectOfficeScene, type OfficeScene } from "./officeScene";
import "./office.css";

type Props = {
  project: Project;
  agents: Agent[];
  execution?: OfficeExecution;
  close: () => void;
  openAgent: (agent: Agent) => void;
};

export default function ProjectOffice({ project, agents, execution, close, openAgent }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const scene = useRef<OfficeScene | null>(null);
  const [sceneError, setSceneError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [overhead, setOverhead] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const members = useMemo(() => officeMembers(project, agents), [project, agents]);
  const selected = members.find(a => a.id === selectedId);
  const rosterKey = JSON.stringify(members.map(a => [a.id, a.name, a.kind]));
  // Status updates change the actors, without recreating the renderer or camera.
  const latest = useRef({ members, execution });
  useEffect(() => { latest.current = { members, execution }; });

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => {
      element.close();
    };
  }, []);

  useEffect(() => {
    setSceneError("");
    setOverhead(false);
    let controller: OfficeScene | null = null;
    try {
      controller = createProjectOfficeScene(viewport.current!, project, latest.current.members, setSelectedId, setSceneError);
      scene.current = controller;
      controller.update(latest.current.members, latest.current.execution);
    } catch {
      setSceneError("No se pudo iniciar el 3D. Comprueba que la aceleración gráfica y WebGL estén habilitados en tu navegador.");
    }
    return () => {
      controller?.dispose();
      scene.current = null;
    };
  }, [project.id, project.name, rosterKey, attempt]);

  useEffect(() => { scene.current?.update(members, execution); }, [members, execution]);
  const working = members.filter(a => officePresence(a, execution).working).length;
  function select(agent: Agent) {
    setSelectedId(agent.id);
    scene.current?.select(agent.id);
  }
  function view(top: boolean) {
    setOverhead(top);
    scene.current?.view(top);
  }

  return (
    <dialog ref={dialog} className="office-dialog" aria-labelledby="office-title" aria-describedby="office-description" onCancel={e => { e.preventDefault(); close(); }}>
      <header className="office-header">
        <span className="office-brand"><Box size={22} /></span>
        <div><span className="office-eyebrow">TU ESPACIO · OFICINA 3D</span><h2 id="office-title">{project.name}</h2></div>
        <span className="office-project-tag">Contexto del proyecto</span>
        <button className="office-close" onClick={close} aria-label="Cerrar oficina 3D"><X size={20} /><span>Salir de la oficina</span></button>
      </header>
      <div className="office-body">
        <section className="office-stage" aria-label="Vista de la oficina">
          <div className="office-scene-heading"><span className="office-eyebrow">UN LUGAR PARA TU EQUIPO</span><h3>Las ideas toman espacio.</h3><p id="office-description">Selecciona un personaje o su puesto para conocer su actividad.</p></div>
          <div className="office-viewport" ref={viewport} />
          {sceneError ? <div className="office-scene-error" role="alert"><Box size={28} /><strong>La vista 3D no está disponible</strong><p>{sceneError}</p><button onClick={() => setAttempt(n => n + 1)}><RotateCcw size={15} /> Reintentar</button><span>Puedes abrir las conversaciones desde el equipo.</span></div> : null}
          <div className="office-scene-bottom">
            <p>Arrastra para girar · Rueda o pellizca para acercar</p>
            <div className="office-camera" role="group" aria-label="Controles de cámara">
              <button onClick={() => view(false)} title="Restablecer cámara" aria-label="Restablecer cámara"><RotateCcw size={17} /></button>
              <button onClick={() => view(!overhead)} aria-pressed={overhead} title="Vista superior" aria-label="Vista superior"><Focus size={18} /></button>
              <span />
              <button onClick={() => scene.current?.zoom(1 / 1.2)} aria-label="Alejar"><Minus size={17} /></button>
              <button onClick={() => scene.current?.zoom(1.2)} aria-label="Acercar"><Plus size={17} /></button>
              <button onClick={() => { const el = dialog.current; if (document.fullscreenElement) void document.exitFullscreen().catch(() => {}); else if (el?.requestFullscreen) void el.requestFullscreen().catch(() => {}); }} aria-label="Alternar pantalla completa" title="Pantalla completa"><Maximize2 size={16} /></button>
            </div>
          </div>
          <div className="office-scene-caption"><i /> OFICINA DE {project.name}<span>{members.length} puestos · {execution ? working + " trabajando" : "Estado sin confirmar"}</span></div>
        </section>
        <aside className="office-team" aria-label="Equipo de este proyecto">
          <div className="office-team-heading"><span className="office-eyebrow">PERSONAS + AGENTES</span><h3>Tu equipo <span>{members.length}</span></h3><p>Cada rol, en su lugar.</p></div>
          <div className="office-roster">
            {members.map(agent => {
              const presence = officePresence(agent, execution);
              return <button key={agent.id} className={"office-member " + (selectedId === agent.id ? "selected" : "")} onClick={() => select(agent)} aria-pressed={selectedId === agent.id}>
                <span className="office-member-avatar" style={{ background: officeColors[agent.kind] }}>{agent.name.slice(0, 1).toLocaleUpperCase("es")}</span>
                <span><strong>{agent.name}</strong><small>{agentRoles[agent.kind]}</small><span className={"office-presence " + presence.tone}><i />{presence.label}</span></span>
                <ArrowUpRight size={15} />
              </button>;
            })}
            {!members.length ? <p className="office-no-team">Este proyecto todavía no tiene agentes. Añádelos desde Plantillas para ver sus puestos aquí.</p> : null}
          </div>
          {selected ? <div className="office-agent-detail" aria-live="polite">
            <span className="office-eyebrow">{agentRoles[selected.kind]}</span><h3>{selected.name}</h3>
            <p>{officePresence(selected, execution).detail}</p>
            <button className="office-chat-button" onClick={() => { if (document.fullscreenElement) void document.exitFullscreen().catch(() => {}); openAgent(selected); }}><MessageCircle size={17} /> Abrir conversación <ArrowUpRight size={15} /></button>
          </div> : <div className="office-agent-detail"><MessageCircle size={22} /><h3>Acércate a una idea.</h3><p>Elige a alguien del equipo y abre su conversación para continuar el trabajo.</p></div>}
          <footer className="office-team-footer"><span className={"office-live-dot " + (execution ? "connected" : "")} />{execution ? "Actividad consultada al servidor" : "Estado de ejecución sin confirmar"}<small>Los agentes trabajan desde sus conversaciones.</small></footer>
        </aside>
      </div>
    </dialog>
  );
}
