import { useCallback, useEffect, useRef, useState } from "react";
import { spokenText } from "./voiceUtils";

export function useSpeechPlayback() {
  const supported = typeof window.speechSynthesis !== "undefined" && typeof SpeechSynthesisUtterance !== "undefined";
  const [enabled, setEnabled] = useState(true);
  const enabledRef = useRef(enabled);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  // Keep utterances alive until the browser finishes playback.
  const utterances = useRef<SpeechSynthesisUtterance[]>([]);
  const stop = useCallback(() => {
    generation.current++;
    if (supported) window.speechSynthesis.cancel();
    utterances.current = [];
    setSpeaking(false);
  }, [supported]);
  useEffect(() => {
    enabledRef.current = enabled;
    if (!enabled) stop();
  }, [enabled, stop]);
  useEffect(() => () => {
    generation.current++;
    if (supported) window.speechSynthesis.cancel();
    utterances.current = [];
  }, [supported]);

  const read = useCallback((content: string, force = false) => {
    if (!supported || (!force && !enabledRef.current)) return;
    stop();
    setError("");
    const text = spokenText(content);
    if (!text) return;
    const token = generation.current;
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find((item) => item.lang === "es-CO") ?? voices.find((item) => item.lang.startsWith("es"));
    const chunks = text.match(/.{1,450}(?:\s|$)|\S{1,450}/g) ?? [text];
    const queue = chunks.map((chunk) => {
      const utterance = new SpeechSynthesisUtterance(chunk);
      utterance.lang = voice?.lang || "es-CO";
      if (voice) utterance.voice = voice;
      utterance.onerror = (event) => {
        if (token !== generation.current) return;
        stop();
        if (event.error !== "canceled" && event.error !== "interrupted")
          setError("No se pudo reproducir la voz. Puedes leer la respuesta en pantalla o volver a pulsar Escuchar.");
      };
      return utterance;
    });
    queue[queue.length - 1].onend = () => {
      if (token !== generation.current) return;
      setSpeaking(false);
      utterances.current = [];
    };
    utterances.current = queue;
    setSpeaking(true);
    queue.forEach((utterance) => window.speechSynthesis.speak(utterance));
  }, [stop, supported]);

  return { supported, enabled, setEnabled, speaking, read, stop, error };
}

export type SpeechPlayback = ReturnType<typeof useSpeechPlayback>;
