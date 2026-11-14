import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  authenticatedFetch,
  clearAccessToken,
  getActiveAccessToken,
  markWorkspaceReturn,
  saveAccessToken,
} from "../lib/session";

type AuthMode = "login" | "register";

type TokenResponse = {
  access_token: string;
};

type ApiProblem = {
  detail?: string | Array<{ msg?: string }>;
};

function getProblemMessage(problem: ApiProblem): string {
  if (typeof problem.detail === "string") return problem.detail;
  if (Array.isArray(problem.detail) && problem.detail[0]?.msg) {
    return problem.detail[0].msg;
  }
  return "Nem sikerült a kérés. Próbáld újra.";
}

function returnToApp(): void {
  if (window.location.pathname === "/auth/workspace") {
    markWorkspaceReturn();
  }
  window.location.assign(
    window.location.pathname === "/auth/profile" ? "/profile" : "/",
  );
}

export default function LoginRegisterPage() {
  const [mode, setMode] = useState<AuthMode>(
    window.location.pathname === "/register" ? "register" : "login",
  );
  const [isBusy, setIsBusy] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    getActiveAccessToken()
      .then((token) => {
        if (cancelled) return;
        if (!token) {
          setIsCheckingSession(false);
          return;
        }
        return authenticatedFetch("/api/auth/me").then((response) => {
          if (cancelled) return;
          if (!response.ok) throw new Error("A munkamenet lejárt.");
          returnToApp();
        });
      })
      .catch(() => {
        if (cancelled) return;
        clearAccessToken();
        setIsCheckingSession(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    setIsBusy(true);

    const formData = new FormData(event.currentTarget);
    const credentials = {
      email: String(formData.get("email") ?? "").trim(),
      password: String(formData.get("password") ?? ""),
    };

    try {
      const endpoint = mode === "login" ? "login" : "register";
      const response = await fetch(`/api/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(credentials),
      });
      const body = (await response.json().catch(() => ({}))) as TokenResponse & ApiProblem;

      if (!response.ok) throw new Error(getProblemMessage(body));
      if (!body.access_token) throw new Error("Az API nem adott vissza bejelentkezési tokent.");

      saveAccessToken(body.access_token);
      returnToApp();
    } catch (error: unknown) {
      setErrorMessage(error instanceof Error ? error.message : "Nem sikerült a kérés.");
    } finally {
      setIsBusy(false);
    }
  }

  if (isCheckingSession) {
    return <main className="page-shell"><p role="status">Munkamenet ellenőrzése…</p></main>;
  }

  return (
    <main className="page-shell">
      <section className="auth-card" aria-labelledby="auth-title">
        <a className="back-link" href="/">← Főoldal</a>
        <header className="card-header">
          <div className="brand-mark" aria-hidden="true">P↔D</div>
          <p className="eyebrow">PDF ↔ DOCX KONVERTER</p>
          <h1 id="auth-title">{mode === "login" ? "Bejelentkezés" : "Fiók létrehozása"}</h1>
          <p className="subtitle">
            {mode === "login" ? "Lépj be a folytatáshoz." : "Regisztrálj az alkalmazás használatához."}
          </p>
        </header>

        <div className="mode-switch" role="tablist" aria-label="Fiókművelet">
          <button
            className={mode === "login" ? "active" : ""}
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            onClick={() => {
              setMode("login");
              setErrorMessage("");
            }}
          >
            Bejelentkezés
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            onClick={() => {
              setMode("register");
              setErrorMessage("");
            }}
          >
            Regisztráció
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email">E-mail-cím</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="nev@pelda.hu"
            required
          />

          <label htmlFor="password">Jelszó</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={mode === "register" ? 8 : 1}
            maxLength={128}
            required
          />
          {mode === "register" && <p className="field-hint">Legalább 8 karakter legyen.</p>}

          {errorMessage && <p className="error-message" role="alert">{errorMessage}</p>}

          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "Feldolgozás…" : mode === "login" ? "Bejelentkezés" : "Regisztráció"}
          </button>
        </form>
      </section>
    </main>
  );
}
