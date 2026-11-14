import { useEffect, useState } from "react";
import ConverterWorkspace from "./ConverterWorkspace";
import "./HomePage.css";
import {
  authenticatedFetch,
  clearAccessToken,
  consumeWorkspaceReturn,
} from "../lib/session";

export default function HomePage() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  useEffect(() => {
    if (!consumeWorkspaceReturn()) return;
    window.requestAnimationFrame(() => {
      document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth" });
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    authenticatedFetch("/api/auth/me")
      .then((response) => {
        if (!response.ok) throw new Error("Unauthorized");
        if (!cancelled) setIsLoggedIn(true);
      })
      .catch(() => {
        if (cancelled) return;
        clearAccessToken();
        setIsLoggedIn(false);
      })
      .finally(() => {
        if (!cancelled) setIsCheckingSession(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page-shell">
      <header className="home-nav">
        <a className="wordmark" href="/" aria-label="PDF és DOCX konverter főoldal">
          <span className="brand-mark" aria-hidden="true">P↔D</span>
          <span>PDF ↔ DOCX</span>
        </a>
        <nav className="nav-actions" aria-label="Fiók">
          {isLoggedIn && (
            <a className="nav-link" href="/profile">
              Profil
            </a>
          )}
          {!isLoggedIn && (
            <a className="nav-link" href="/auth">
              {isCheckingSession ? "Ellenőrzés…" : "Bejelentkezés"}
            </a>
          )}
        </nav>
      </header>

      <section className="home-card" aria-labelledby="home-title">
        <p className="eyebrow">DOKUMENTUMKEZELÉS</p>
        <h1 id="home-title">PDF és DOCX,<br />egyszerűen.</h1>
        <p className="subtitle">
          Válaszd ki a konverzió irányát, majd add hozzá a dokumentumot. A tényleges
          átalakítás bekötése még folyamatban van.
        </p>
      </section>

      <section className="workspace-card" id="workspace" aria-labelledby="workspace-title">
        <header className="workspace-header">
          <p className="eyebrow">MUNKAFELÜLET</p>
          <h2 id="workspace-title">PDF és DOCX konvertálása</h2>
        </header>
        <ConverterWorkspace />
      </section>

      <footer className="home-footer">PDF ↔ DOCX konverter</footer>
    </main>
  );
}
