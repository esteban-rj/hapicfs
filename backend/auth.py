"""Single-owner authentication for the local platform."""
from __future__ import annotations

import hashlib
import math
import os
import secrets
import threading
import time
import unicodedata
from time import monotonic

from fastapi import HTTPException

from .storage import now


DEFAULT_USERNAME = "norteños"
DEFAULT_PASSWORD_HASH = "pbkdf2_sha256$600000$76b49a542ad09e15120fe1ef1ba681ec$12c7249086b64b57159d4ed1d09dff4816dac97086938804778e106a2ca05083"
SESSION_SECONDS = 24 * 60 * 60
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 5 * 60


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


class Authentication:
    def __init__(self, store):
        self.store = store
        self.username = unicodedata.normalize("NFC", os.getenv("HAPIC_LOGIN_USERNAME", DEFAULT_USERNAME).strip())
        self.password_hash = os.getenv("HAPIC_LOGIN_PASSWORD_HASH", DEFAULT_PASSWORD_HASH)
        try:
            algorithm, iterations, salt, digest = self.password_hash.split("$")
            if algorithm != "pbkdf2_sha256" or iterations != "600000" or len(bytes.fromhex(salt)) != 16 or len(bytes.fromhex(digest)) != 32 or not self.username:
                raise ValueError
        except ValueError:
            raise ValueError("Configura un usuario y un hash PBKDF2 válidos para el inicio de sesión.") from None
        self.salt = salt
        self.fingerprint = hashlib.sha256((self.username + "\0" + self.password_hash).encode()).hexdigest()
        self.attempts: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def session(self, token: str):
        return self.store.one(
            "SELECT * FROM sessions WHERE token=? AND expires_at>? AND credential_fingerprint=?",
            (token, int(time.time()), self.fingerprint),
        )

    def login(self, username: str, password: str, address: str, previous_token: str = ""):
        timestamp = monotonic()
        with self.lock:
            self.attempts = {key: [value for value in values if value > timestamp - LOGIN_WINDOW_SECONDS]
                             for key, values in self.attempts.items() if values[-1] > timestamp - LOGIN_WINDOW_SECONDS}
            attempts = self.attempts.setdefault(address, [])
            if len(attempts) >= MAX_LOGIN_ATTEMPTS:
                retry_after = max(1, math.ceil(attempts[0] + LOGIN_WINDOW_SECONDS - timestamp))
                raise HTTPException(429, "Demasiados intentos. Vuelve a intentarlo en unos minutos.", headers={"Retry-After": str(retry_after)})
            # Reserve the attempt before hashing so concurrent guesses are limited too.
            attempts.append(timestamp)
        candidate = password_hash(password, self.salt)
        valid_password = secrets.compare_digest(candidate, self.password_hash)
        valid_username = secrets.compare_digest(unicodedata.normalize("NFC", username.strip()).encode(), self.username.encode())
        if not (valid_username and valid_password):
            raise HTTPException(401, "Usuario o contraseña incorrectos.")
        with self.lock:
            self.attempts.pop(address, None)
        return self.issue_session(previous_token)

    def issue_session(self, previous_token: str = ""):
        session = {"token": secrets.token_urlsafe(32), "csrf": secrets.token_urlsafe(32), "created_at": now(),
                   "expires_at": int(time.time()) + SESSION_SECONDS, "credential_fingerprint": self.fingerprint}
        with self.store.db() as db:
            db.execute("DELETE FROM sessions WHERE token=? OR expires_at<=? OR credential_fingerprint<>?",
                       (previous_token, int(time.time()), self.fingerprint))
            db.execute("INSERT INTO sessions(token,csrf,created_at,expires_at,credential_fingerprint) VALUES (:token,:csrf,:created_at,:expires_at,:credential_fingerprint)", session)
        return session

    def logout(self, token: str):
        with self.store.db() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (token,))
            db.execute("DELETE FROM oauth_states WHERE session_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def bootstrap(self, session):
        return {"csrf": session["csrf"], "user": {"id": "local-owner", "name": self.username}, "mode": "local"}
