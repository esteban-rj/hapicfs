// A real API and SQLite store in a disposable directory, without provider keys.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { pbkdf2Sync, randomBytes } from "node:crypto";

const root = fileURLToPath(new URL("../../", import.meta.url));
const localPython = join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = process.env.HAPIC_TEST_PYTHON || (existsSync(localPython) ? localPython : "python3");
const data = mkdtempSync(join(tmpdir(), "hapic-office-browser-"));
const username = process.env.HAPIC_TEST_LOGIN_USERNAME || "office-test-user";
const password = process.env.HAPIC_TEST_LOGIN_PASSWORD || "office-browser-test-password";
const salt = randomBytes(16);
const passwordHash = `pbkdf2_sha256$600000$${salt.toString("hex")}$${pbkdf2Sync(password, salt, 600_000, 32, "sha256").toString("hex")}`;
const server = spawn(python, ["-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8011"], {
  cwd: root, stdio: "inherit", env: { ...process.env, HAPIC_DATA_DIR: data, OPENAI_API_KEY: "", HAPIC_YOUTUBE_CLIENT_FILE: "",
    HAPIC_LOGIN_USERNAME: username, HAPIC_LOGIN_PASSWORD_HASH: passwordHash },
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("error", error => { console.error(error.message); rmSync(data, { recursive: true, force: true }); process.exit(1); });
server.on("exit", code => { rmSync(data, { recursive: true, force: true }); process.exit(code || 0); });
