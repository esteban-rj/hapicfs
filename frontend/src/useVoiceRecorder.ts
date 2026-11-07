import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { MAX_AUDIO_BYTES, MAX_RECORDING_SECONDS } from "./voiceUtils";

type RecordingState = "idle" | "requesting" | "recording" | "transcribing";

export function useVoiceRecorder(agentId: string, onTranscript: (text: string) => void) {
  const supported = window.isSecureContext && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
  const [state, setState] = useState<RecordingState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const session = useRef(0);
  const engaged = useRef(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const request = useRef<AbortController | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);

  const release = useCallback(() => {
    clearInterval(timer.current);
    clearTimeout(timeout.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);
  const discard = useCallback(() => {
    session.current++;
    engaged.current = false;
    request.current?.abort();
    request.current = null;
    if (recorder.current) {
      recorder.current.ondataavailable = null;
      recorder.current.onstop = null;
      recorder.current.onerror = null;
      if (recorder.current.state !== "inactive") recorder.current.stop();
      recorder.current = null;
    }
    release();
  }, [release]);
  const cancel = useCallback(() => {
    discard();
    setState("idle");
    setSeconds(0);
  }, [discard]);
  useEffect(() => () => { discard(); }, [agentId, discard]);

  const stop = useCallback(() => {
    if (recorder.current?.state === "recording") {
      setState("transcribing");
      recorder.current.stop();
      release();
    }
  }, [release]);

  async function start() {
    if (!supported) {
      setError("El micrófono requiere un navegador compatible y HTTPS o localhost. Puedes seguir escribiendo.");
      return;
    }
    // Also guards rapid clicks while the browser is asking for permission.
    if (engaged.current) return;
    engaged.current = true;
    const token = ++session.current;
    setState("requesting");
    setError("");
    setSeconds(0);
    try {
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error("unsupported-format");
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (token !== session.current) {
        audioStream.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = audioStream;
      const capture = new MediaRecorder(audioStream, { mimeType });
      recorder.current = capture;
      const chunks: Blob[] = [];
      let size = 0;
      capture.ondataavailable = (event) => {
        if (token !== session.current || !event.data.size) return;
        size += event.data.size;
        if (size > MAX_AUDIO_BYTES) {
          cancel();
          setError("La grabación superó 8 MB. Graba un mensaje más breve.");
        } else chunks.push(event.data);
      };
      capture.onerror = () => {
        if (token !== session.current) return;
        cancel();
        setError("Se interrumpió el micrófono. Comprueba el dispositivo y vuelve a grabar.");
      };
      capture.onstop = async () => {
        release();
        if (token !== session.current) return;
        recorder.current = null;
        setState("transcribing");
        const controller = new AbortController();
        request.current = controller;
        try {
          const audio = new Blob(chunks, { type: capture.mimeType || mimeType });
          if (!audio.size) throw new Error("La grabación está vacía. Vuelve a grabar.");
          const result = await api<{ text: string }>(`/agents/${agentId}/voice/transcriptions`, {
            method: "POST", headers: { "Content-Type": audio.type }, body: audio, signal: controller.signal,
          });
          if (token === session.current) onTranscriptRef.current(result.text);
        } catch (reason) {
          if (token === session.current) setError(reason instanceof Error ? reason.message : "No se pudo transcribir el audio.");
        } finally {
          if (token === session.current) {
            engaged.current = false;
            request.current = null;
            setState("idle");
          }
        }
      };
      capture.start(1000);
      setState("recording");
      const started = Date.now();
      timer.current = setInterval(() => setSeconds(Math.min(MAX_RECORDING_SECONDS, Math.floor((Date.now() - started) / 1000))), 250);
      timeout.current = setTimeout(stop, MAX_RECORDING_SECONDS * 1000);
    } catch (reason) {
      if (token !== session.current) return;
      discard();
      setState("idle");
      const name = reason instanceof Error ? reason.name : "";
      setError(name === "NotAllowedError" || name === "SecurityError"
        ? "Permite el acceso al micrófono en tu navegador y vuelve a intentarlo."
        : name === "NotFoundError"
          ? "No se encontró un micrófono. Conecta uno y vuelve a intentarlo."
          : "No se pudo iniciar la grabación. Comprueba que tu navegador admita audio WebM o MP4 y que el micrófono esté disponible.");
    }
  }

  return { supported, state, seconds, error, start, stop, cancel };
}
