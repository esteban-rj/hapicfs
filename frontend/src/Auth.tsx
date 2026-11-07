import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole } from "lucide-react";
import { ApiError, bootstrap, login, logout, type Session } from "./api";
import { Mark } from "./components";

export function AuthGate({ children }: { children: (session: Session, signOut: () => Promise<void>) => ReactNode }) {
  const [session, setSession] = useState<Session>();
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const expired = () => {
      setSession(undefined);
      setError("");
    };
    window.addEventListener("hapic:unauthorized", expired);
    setChecking(true);
    setError("");
    bootstrap()
      .then((result) => { if (active) setSession(result); })
      .catch((reason) => {
        if (active && !(reason instanceof ApiError && reason.status === 401)) {
          setError("No se pudo conectar con Hapic. Comprueba la conexión y vuelve a intentarlo.");
        }
      })
      .finally(() => { if (active) setChecking(false); });
    return () => {
      active = false;
      window.removeEventListener("hapic:unauthorized", expired);
    };
  }, [attempt]);

  async function signOut() {
    await logout();
    setSession(undefined);
  }

  if (checking || error) {
    return <main className="login-screen">
      <div className="login-status" role={error ? "alert" : "status"}>
        <div className="login-brand"><Mark small /><span>Hapic</span></div>
        {checking ? <><LoaderCircle className="spin" size={22} /><p>Comprobando sesión…</p></> : <>
          <p>{error}</p>
          <button className="primary" onClick={() => setAttempt((value) => value + 1)}>Volver a intentar</button>
        </>}
      </div>
    </main>;
  }
  if (!session) return <Login onLogin={setSession} />;
  return children(session, signOut);
}

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const passwordInput = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const session = await login(username, password);
      setPassword("");
      onLogin(session);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No se pudo conectar. Vuelve a intentarlo.");
      setPassword("");
      requestAnimationFrame(() => passwordInput.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  return <main className="login-screen">
    <div className="login-shell">
      <div className="login-brand"><Mark small /><span>Hapic</span></div>
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-icon"><LockKeyhole size={22} /></div>
        <h1 id="login-title">Inicia sesión</h1>
        <p className="login-intro">Accede a tus proyectos y a tu equipo de agentes.</p>
        <form onSubmit={submit} aria-busy={busy}>
          <label htmlFor="login-username">Usuario</label>
          <input id="login-username" name="username" autoComplete="username" autoFocus required maxLength={80}
            placeholder="Tu usuario" value={username} onChange={(event) => setUsername(event.target.value)}
            disabled={busy} aria-describedby={error ? "login-error" : undefined} />
          <label htmlFor="login-password">Contraseña</label>
          <div className="login-password">
            <input ref={passwordInput} id="login-password" name="password" type={visible ? "text" : "password"}
              autoComplete="current-password" required maxLength={256} placeholder="Tu contraseña"
              value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy}
              aria-describedby={error ? "login-error" : undefined} />
            <button type="button" className="login-visibility" onClick={() => setVisible((value) => !value)}
              aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={visible} disabled={busy}>
              {visible ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {error ? <p className="login-error" id="login-error" role="alert">{error}</p> : null}
          <button type="submit" className="primary login-submit" disabled={busy}>
            {busy ? <><LoaderCircle className="spin" size={17} />Iniciando sesión…</> : <>Iniciar sesión<ArrowRight size={17} /></>}
          </button>
        </form>
      </section>
      <p className="login-footer">Tu espacio para crear, coordinar y avanzar.</p>
    </div>
  </main>;
}
