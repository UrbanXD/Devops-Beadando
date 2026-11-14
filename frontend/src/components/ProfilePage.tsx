import { useEffect, useState } from "react";
import { authenticatedFetch, clearAccessToken } from "../lib/session";

type Profile = {
  email: string;
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    let cancelled = false;
    authenticatedFetch("/api/auth/me")
      .then(async (response) => {
        if (!response.ok) throw new Error("Unauthorized");
        return (await response.json()) as Profile;
      })
      .then((currentProfile) => {
        if (!cancelled) setProfile(currentProfile);
      })
      .catch(() => {
        if (cancelled) return;
        clearAccessToken();
        window.location.replace("/auth/profile");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function logOut() {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Clear the local access token even if the API is temporarily unavailable.
    } finally {
      clearAccessToken();
      window.location.assign("/");
    }
  }

  if (!profile) {
    return (
      <main className="page-shell">
        <p role="status">Profil betöltése…</p>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <div className="profile-page">
        <header className="profile-heading">
          <a className="back-link" href="/">← Főoldal</a>
          <p className="eyebrow">FIÓK</p>
          <h1>Profil</h1>
        </header>

        <section className="profile-card" aria-labelledby="profile-email-heading">
          <div>
            <h2 id="profile-email-heading">E-mail-cím</h2>
            <p className="profile-email">{profile.email}</p>
          </div>
          <button className="logout-button" type="button" onClick={logOut}>
            Kijelentkezés
          </button>
        </section>

        <section className="history-card" aria-labelledby="history-heading">
          <h2 id="history-heading">Előzmények</h2>
          <p>Fejlesztés alatt</p>
        </section>
      </div>
    </main>
  );
}
