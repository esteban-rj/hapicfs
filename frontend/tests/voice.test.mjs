import { test } from "node:test";
import assert from "node:assert/strict";
import { isStatusQuestion, spokenText } from "../src/voiceUtils.ts";

test("short spoken status questions use the status endpoint, including the selected agent's name", () => {
  for (const question of ["¿Cómo vas?", "Nora, ¿qué estás haciendo?", "Oye Nora, ¿cuál es tu estado?", "¿Ya terminaste, Nora?", "¿Tienes tareas pendientes?", "Dime tu estado por favor."]) {
    assert.equal(isStatusQuestion(question, "Nora"), true, question);
  }
});

test("tasks and mixed requests that mention status still go to the selected agent", () => {
  for (const task of ["Crea una pantalla de estado", "Dime tu estado y luego diseña el menú", "¿Cómo vas? También escribe un informe.", "Asigna una tarea a Nora", "Actualiza el estado de las tareas", "Nora, prepara un calendario."]) {
    assert.equal(isStatusQuestion(task, "Nora"), false, task);
  }
});

test("names with accents or punctuation remain usable without interpreting names as regular expressions", () => {
  assert.equal(isStatusQuestion("Óscar (UX), ¿cómo estás?", "Óscar (UX)"), true);
  assert.equal(isStatusQuestion("Diseña el estado de Óscar (UX)", "Óscar (UX)"), false);
});

test("speech preserves the answer and replaces code and URLs with readable references", () => {
  assert.equal(spokenText("## Avance\n- **Listo**: [abrir plan](https://example.com/plan)\n```js\nsecretCode();\n```\nMira https://example.com/preview"), "Avance Listo: abrir plan Hay un bloque de código en el chat. Mira enlace en el chat");
  assert.equal(spokenText("Preparé ![el diagrama](agents/a/workspace/image.png)."), "Preparé el diagrama.");
});
