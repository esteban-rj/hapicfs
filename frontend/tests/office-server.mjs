// A real API and SQLite store in a disposable directory, without provider keys.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const localPython = join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = process.env.HAPIC_TEST_PYTHON || (existsSync(localPython) ? localPython : "python3");
const data = mkdtempSync(join(tmpdir(), "hapic-office-browser-"));
const server = spawn(python, ["-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8011"], {
  cwd: root, stdio: "inherit", env: { ...process.env, HAPIC_DATA_DIR: data, OPENAI_API_KEY: "", HAPIC_YOUTUBE_CLIENT_FILE: "" },
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("error", error => { console.error(error.message); rmSync(data, { recursive: true, force: true }); process.exit(1); });
server.on("exit", code => { rmSync(data, { recursive: true, force: true }); process.exit(code || 0); });
