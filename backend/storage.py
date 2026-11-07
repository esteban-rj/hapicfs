from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gpt-6.1-sol"
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid4().hex[:16]}"


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.secrets_dir = self.root / "secrets"
        self.secrets_dir.mkdir(exist_ok=True, mode=0o700)
        keyfile = self.secrets_dir / "master.key"
        if not keyfile.exists():
            keyfile.write_bytes(Fernet.generate_key())
            keyfile.chmod(0o600)
        self.fernet = Fernet(keyfile.read_bytes())
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS memberships(user_id TEXT,organization_id TEXT REFERENCES organizations(id),role TEXT,PRIMARY KEY(user_id,organization_id));
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,organization_id TEXT REFERENCES organizations(id),name TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY,organization_id TEXT,project_id TEXT REFERENCES projects(id),name TEXT,kind TEXT,template TEXT,model TEXT,effort TEXT,status TEXT,container_id TEXT,error TEXT,created_at TEXT,UNIQUE(project_id,name));
            CREATE UNIQUE INDEX IF NOT EXISTS one_hapic_per_project ON agents(project_id) WHERE kind='hapic';
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,agent_id TEXT REFERENCES agents(id),role TEXT,content TEXT,source TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,agent_id TEXT REFERENCES agents(id),message TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,csrf TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY,agent_id TEXT REFERENCES agents(id),message_id INTEGER REFERENCES messages(id),path TEXT,mime_type TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS connections(
                id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),provider TEXT NOT NULL,
                account_id TEXT NOT NULL,account_name TEXT NOT NULL,scopes TEXT NOT NULL,status TEXT NOT NULL,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(project_id,provider,account_id));
            CREATE TABLE IF NOT EXISTS agent_tools(
                agent_id TEXT NOT NULL REFERENCES agents(id),tool_id TEXT NOT NULL,
                connection_id TEXT REFERENCES connections(id),enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(agent_id,tool_id));
            CREATE TABLE IF NOT EXISTS oauth_states(
                state_hash TEXT PRIMARY KEY,session_hash TEXT NOT NULL,project_id TEXT NOT NULL REFERENCES projects(id),
                verifier TEXT NOT NULL,redirect_uri TEXT NOT NULL,client_fingerprint TEXT NOT NULL,expires_at INTEGER NOT NULL);
            INSERT OR IGNORE INTO agent_tools(agent_id,tool_id,enabled)
                SELECT id,'youtube',1 FROM agents WHERE kind='community-manager';
            ''')
            if "planner_id" not in {row[1] for row in db.execute("PRAGMA table_info(agents)")}:
                db.execute("ALTER TABLE agents ADD COLUMN planner_id TEXT REFERENCES agents(id)")

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.root / "platform.db", timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def all(self, sql, args=()):
        with self.db() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.db() as db:
            db.execute(sql, args)

    def setting(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        self.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def secret(self, name, value=None):
        path = self.secrets_dir / (name + ".enc")
        if value is not None:
            path.write_bytes(self.fernet.encrypt(value.encode()))
            path.chmod(0o600)
        return self.fernet.decrypt(path.read_bytes()).decode() if path.exists() else None

    def api_key(self):
        return os.getenv("OPENAI_API_KEY") or self.secret("openai")

    def token(self, agent_id, kind):
        key = f"{agent_id}-{kind}"
        return self.secret(key) or self.secret(key, secrets.token_urlsafe(40))

    def project_path(self, project):
        return self.root / "organizations" / project["organization_id"] / "projects" / project["id"]

    def agent_path(self, agent):
        return self.project_path({"organization_id": agent["organization_id"], "id": agent["project_id"]}) / "agents" / agent["id"]

    def event(self, agent_id, message):
        self.execute("INSERT INTO events(agent_id,message,created_at) VALUES (?,?,?)", (agent_id, message, now()))

    def message(self, agent_id, role, content, source="hermes"):
        with self.db() as db:
            return db.execute("INSERT INTO messages(agent_id,role,content,source,created_at) VALUES (?,?,?,?,?)", (agent_id, role, content, source, now())).lastrowid
