import { useEffect, useRef, useState, type FormEvent } from "react";
import { Activity, LoaderCircle, Mic, Send, Square, Volume2, X } from "lucide-react";
import { api, type Agent } from "./api";
import { useVoiceRecorder } from "./useVoiceRecorder";
import { type SpeechPlayback } from "./useSpeechPlayback";
import { isStatusQuestion, MAX_RECORDING_SECONDS } from "./voiceUtils";

type StatusReply = { content: string; checked_at: string };

export function VoicePanel({ agent, configured, canSend, onSend, speech }: {
  agent: Agent;
  configured: boolean;
  canSend: boolean;
  onSend: (text: string, requestId: string) => Promise<string>;
  speech: SpeechPlayback;
}) {
  const [draft, setDraft] = useState("");
  const [intent, setIntent] = useState<"message" | "status">("message");
  const [sending, setSending] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<StatusReply>();
  const mounted = useRef(false);
  const messageInFlight = useRef(false);
  const statusInFlight = useRef(false);
  const draftVersion = useRef(0);
  const interaction = useRef(0);
  const request = useRef<AbortController | null>(null);
  const submission = useRef<{ text: string; id: string } | null>(null);
  const transcript = useRef<HTMLTextAreaElement>(null);
  function updateDraft(text: string) {
    draftVersion.current++;
    setDraft(text);
    setIntent(isStatusQuestion(text, agent.name) ? "status" : "message");
  }
  const recorder = useVoiceRecorder(agent.id, (text) => {
    updateDraft(text);
    setError("");
    transcript.current?.focus();
  });
  const capturing = recorder.state !== "idle";
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; request.current?.abort(); };
  }, [agent.id]);
  useEffect(() => { if (draft) transcript.current?.focus(); }, [!!draft]);

  async function readStatus(token: number) {
    const controller = new AbortController();
    request.current = controller;
    try {
      const result = await api<StatusReply>(`/agents/${agent.id}/voice/status`, { signal: controller.signal });
      if (mounted.current) {
        setStatus(result);
        if (token === interaction.current) speech.read(result.content);
      }
    } finally { if (request.current === controller) request.current = null; }
  }

  async function submit(event?: FormEvent, statusOnly = false) {
    event?.preventDefault();
    const isStatus = statusOnly || intent === "status";
    if (capturing || (isStatus ? statusInFlight.current : messageInFlight.current || !canSend) || (!statusOnly && !draft.trim())) return;
    const token = ++interaction.current;
    const version = draftVersion.current;
    if (isStatus) { statusInFlight.current = true; setChecking(true); }
    else { messageInFlight.current = true; setSending(true); }
    setError("");
    speech.stop();
    try {
      if (isStatus) {
        await readStatus(token);
      } else {
        const text = draft.trim();
        if (submission.current?.text !== text) submission.current = { text, id: crypto.randomUUID() };
        const reply = await onSend(text, submission.current.id);
        if (mounted.current && token === interaction.current) speech.read(reply);
      }
      if (mounted.current && !statusOnly && version === draftVersion.current) {
        updateDraft("");
        if (!isStatus) submission.current = null;
      }
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "No se pudo completar la solicitud de voz.");
    } finally {
      if (isStatus) {
        statusInFlight.current = false;
        if (mounted.current) setChecking(false);
      } else {
        messageInFlight.current = false;
        if (mounted.current) setSending(false);
      }
    }
  }

  return <section className="voice-panel" aria-label={`Comunicación por voz con ${agent.name}`}>
    <div className="voice-toolbar">
      <button type="button" className={`secondary voice-mic${recorder.state === "recording" ? " recording" : ""}`}
        disabled={checking || recorder.state === "requesting" || recorder.state === "transcribing" || !configured || !recorder.supported}
        aria-label={recorder.state === "recording" ? "Terminar grabación y transcribir" : `Hablar con ${agent.name}`}
        onClick={() => { interaction.current++; speech.stop(); if (recorder.state === "recording") recorder.stop(); else void recorder.start(); }}>
        {recorder.state === "recording" ? <Square size={15} /> : capturing ? <LoaderCircle className="spin" size={15} /> : <Mic size={16} />}
        {recorder.state === "recording" ? `Terminar · ${recorder.seconds}/${MAX_RECORDING_SECONDS} s` : recorder.state === "transcribing" ? "Transcribiendo…" : recorder.state === "requesting" ? "Esperando micrófono…" : "Hablar"}
      </button>
      {capturing ? <button type="button" className="text-button" onClick={recorder.cancel}><X size={14} /> Cancelar grabación</button> : null}
      <button type="button" className="text-button" disabled={checking || capturing} onClick={() => void submit(undefined, true)}>
        {checking ? <LoaderCircle size={15} className="spin" /> : <Activity size={15} />} Consultar estado
      </button>
      {speech.supported ? <label className="voice-auto-read"><input type="checkbox" checked={speech.enabled} onChange={(event) => speech.setEnabled(event.target.checked)} />Leer respuestas</label> : null}
      {speech.speaking ? <button type="button" className="text-button" onClick={speech.stop}><Square size={14} /> Detener voz</button> : null}
    </div>
    <p className="voice-help">
      {!recorder.supported ? "El micrófono requiere un navegador compatible y HTTPS o localhost. Puedes escribir o consultar el estado."
        : !configured ? "Configura OpenAI para usar el micrófono. Puedes consultar el estado sin conexión de IA."
          : recorder.state === "recording" ? `Escuchando para ${agent.name}. Pulsa Terminar al acabar; máximo ${MAX_RECORDING_SECONDS} segundos.`
            : `Habla con ${agent.name}: dicta una tarea o pregunta «¿cómo vas?». Revisa la transcripción antes de enviarla. El audio se envía a OpenAI y puede generar un coste.`}
      {!speech.supported ? " La lectura en voz alta no está disponible en este navegador." : ""}
    </p>
    {draft ? <form className="voice-draft" onSubmit={(event) => void submit(event)}>
      <label htmlFor={`voice-transcript-${agent.id}`}>Transcripción para {agent.name}</label>
      <textarea ref={transcript} id={`voice-transcript-${agent.id}`} rows={3} maxLength={20_000} value={draft} disabled={checking || capturing || (sending && intent === "message")}
        onChange={(event) => updateDraft(event.target.value)} />
      <div className="voice-draft-actions">
        <label>Enviar como<select value={intent} disabled={checking || capturing || (sending && intent === "message")} onChange={(event) => setIntent(event.target.value as "message" | "status")}>
          <option value="message">Mensaje o tarea</option><option value="status">Consulta de estado</option>
        </select></label>
        <button type="button" className="text-button" disabled={checking || capturing || sending} onClick={() => { updateDraft(""); submission.current = null; }}>Descartar</button>
        <button className="primary" disabled={checking || capturing || !draft.trim() || (intent === "message" && (sending || !canSend))}>
          {checking || (sending && intent === "message") ? <LoaderCircle size={14} className="spin" /> : <Send size={14} />}
          {intent === "status" ? "Consultar estado" : `Enviar a ${agent.name}`}
        </button>
      </div>
      {intent === "message" && !canSend ? <p className="voice-help">El agente debe estar conectado y libre para recibir esta tarea. Puedes conservar el texto o consultar su estado mientras tanto.</p> : null}
    </form> : null}
    {status ? <div className="voice-status-reply" role="status">
      <div><strong>Estado de {agent.name}</strong><time dateTime={status.checked_at}>{new Date(status.checked_at).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
        {speech.supported ? <button type="button" className="text-button" onClick={() => speech.read(status.content, true)}><Volume2 size={14} /> Escuchar estado</button> : null}
        <button type="button" className="icon-button" aria-label="Cerrar resumen de estado" onClick={() => setStatus(undefined)}><X size={14} /></button>
      </div>
      <p>{status.content}</p>
    </div> : null}
    {error || recorder.error || speech.error ? <p className="inline-error" role="alert">{error || recorder.error || speech.error}</p> : null}
  </section>;
}
