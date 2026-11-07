import { useEffect, useState, type ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { ApiError, bootstrap, type Session } from "./api";
import { Mark } from "./components";

export function AuthGate({ children }: { children: (session: Session) => ReactNode }) {
  const [session, setSession] = useState<Session>();
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const expired = () => setAttempt((value) => value + 1);
    window.addEventListener("hapic:unauthorized", expired);
    setChecking(true);
    setError("");
    bootstrap()
      .then((result) => { if (active) setSession(result); })
      .catch((reason) => {
        if (!active) return;
        setSession(undefined);
        setError(reason instanceof ApiError ? reason.message : "No se pudo conectar con Hapic. Comprueba la conexión y vuelve a intentarlo.");
      })
      .finally(() => { if (active) setChecking(false); });
    return () => {
      active = false;
      window.removeEventListener("hapic:unauthorized", expired);
    };
  }, [attempt]);

  if (checking || error || !session) {
    return <main className="login-screen">
      <div className="login-status" role={error ? "alert" : "status"}>
        <div className="login-brand"><Mark small /><span>Hapic</span></div>
        {checking || !error ? <><LoaderCircle className="spin" size={22} /><p>Abriendo tu espacio…</p></> : <>
          <p>{error}</p>
          <button className="primary" onClick={() => setAttempt((value) => value + 1)}>Volver a intentar</button>
        </>}
      </div>
    </main>;
  }
  return children(session);
}
