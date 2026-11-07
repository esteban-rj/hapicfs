import { useState } from "react";
import { ArrowRight, Check, Layers, Sparkles } from "lucide-react";
import { Mark } from "./components";

const steps = [
  { title: "Tu idea", label: "Tú", text: "Quiero una web para mi evento y una campaña para darlo a conocer.", detail: "Empieza por el objetivo. Hapic pregunta por lo que falta antes de repartir el trabajo." },
  { title: "El equipo", label: "Hapic · ejemplo", text: "El arquitecto define el plan, el programador construye la web y Mariana prepara los copies y las piezas de la campaña.", detail: "Cada tarea tiene un responsable. Las tareas que dependen de otra esperan su entrega." },
  { title: "La entrega", label: "Equipo · ejemplo", text: "Revisa la web, los textos y las imágenes desde las conversaciones y el panel de Entregables.", detail: "El estado y los resultados de tus tareas reales se consultan al abrir cada agente." },
];

export function TeamDemo({ onStart, hasTeam }: { onStart: () => void; hasTeam: boolean }) {
  const [step, setStep] = useState(0);
  return (
    <aside className="demo-chat-card card team-demo" aria-labelledby="team-demo-title">
      <div className="demo-chat-header"><div className="demo-chat-title"><Mark small /><div><strong id="team-demo-title">De la idea a la entrega</strong><span className="tiny muted">Así colabora tu equipo</span></div></div><span className="team-demo-label">DEMO</span></div>
      <p className="team-demo-intro">Explora el flujo con este ejemplo. No crea tareas ni consume tu API.</p>
      <div className="demo-steps" aria-label="Pasos de la demostración">{steps.map((item, index) => <button key={item.title} type="button" className={step === index ? "selected" : ""} aria-pressed={step === index} onClick={() => setStep(index)}><span>{index < step ? <Check size={12} /> : index + 1}</span>{item.title}</button>)}</div>
      <div className="demo-chat-messages" aria-live="polite"><div className={"demo-message " + (step === 0 ? "user" : "agent")}><div className="demo-bubble"><span className="demo-label">{steps[step].label}</span><p>{steps[step].text}</p></div></div></div>
      <p className="demo-step-detail"><Layers size={16} /><span>{steps[step].detail}</span></p>
      <div className="demo-chat-actions"><button className="text-button" onClick={() => setStep((step + 1) % steps.length)}>{step === 2 ? "Volver al inicio" : "Siguiente paso"}<ArrowRight size={14} /></button></div>
      <div className="demo-start"><Sparkles size={18} /><strong>Ahora, con tu proyecto.</strong><p>Abre Hapic para conversar con tu equipo real.</p><button type="button" className="primary" onClick={onStart}>{hasTeam ? "Ir a Hapic" : "Crear mi primer proyecto"}<ArrowRight size={15} /></button></div>
    </aside>
  );
}
