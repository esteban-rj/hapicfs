export const MAX_RECORDING_SECONDS = 60;
export const MAX_AUDIO_BYTES = 8 * 1024 * 1024;

function normalized(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}

// Match whole, short questions so a task mentioning "estado" is still sent to Hermes.
export function isStatusQuestion(value: string, agentName: string) {
  let question = normalized(value);
  const name = normalized(agentName);
  question = question.replace(/^(?:hola|oye)\s+/, "").replace(/^por favor\s+/, "").replace(/\s+por favor$/, "");
  if (name && question.startsWith(name + " ")) question = question.slice(name.length + 1);
  if (name && question.endsWith(" " + name)) question = question.slice(0, -name.length - 1);
  return /^(?:estado|(?:dime|dame|consulta) (?:tu|el) estado|cual es (?:tu|el) estado|como (?:vas|estas|va el equipo)|(?:en que estas trabajando|que estas haciendo)(?: ahora)?|(?:cual es tu|como va tu) progreso|ya terminaste|has terminado|(?:que tareas tienes|tienes tareas) pendientes|estado de (?:las|tus) tareas)$/.test(question);
}

export function spokenText(value: string) {
  return value
    .replace(/```[\s\S]*?```/g, " Hay un bloque de código en el chat. ")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " enlace en el chat ")
    .replace(/(^|\n)\s{0,3}(?:#{1,6}\s+|[-*>]\s+)/g, "$1")
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ").trim();
}
