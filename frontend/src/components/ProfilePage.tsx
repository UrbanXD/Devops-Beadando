import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import "./ProfilePage.css";
import { authenticatedFetch, clearAccessToken } from "../lib/session";

type Profile = {
  email: string;
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const deleteDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (isDeleteDialogOpen && deleteDialogRef.current && !deleteDialogRef.current.open) {
      deleteDialogRef.current.showModal();
    }
  }, [isDeleteDialogOpen]);

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

  function openDeleteDialog() {
    setDeleteError("");
    setDeletePassword("");
    setIsDeleteDialogOpen(true);
  }

  function closeDeleteDialog() {
    if (isDeletingAccount) return;
    deleteDialogRef.current?.close();
    setIsDeleteDialogOpen(false);
    setDeleteError("");
    setDeletePassword("");
  }

  async function deleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDeleteError("");
    setIsDeletingAccount(true);

    try {
      const response = await authenticatedFetch("/api/auth/me", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: deletePassword }),
      });

      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as {
          detail?: unknown;
        };
        setDeleteError(
          typeof problem.detail === "string"
            ? problem.detail
            : "Nem sikerült törölni a fiókot. Próbáld újra.",
        );
        return;
      }

      clearAccessToken();
      window.location.replace("/");
    } catch {
      setDeleteError("Nem sikerült elérni a szervert. Próbáld újra.");
    } finally {
      setIsDeletingAccount(false);
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
          <div className="profile-actions">
            <button className="logout-button" type="button" onClick={logOut}>
              Kijelentkezés
            </button>
            <button className="delete-account-button" type="button" onClick={openDeleteDialog}>
              Fiók törlése
            </button>
          </div>
        </section>

        <section className="history-card" aria-labelledby="history-heading">
          <h2 id="history-heading">Előzmények</h2>
          <p>Fejlesztés alatt</p>
        </section>
      </div>

      <dialog
        ref={deleteDialogRef}
        className="delete-account-dialog"
        aria-labelledby="delete-account-title"
        onClose={() => {
          setIsDeleteDialogOpen(false);
          setDeletePassword("");
        }}
        onCancel={(event) => {
          if (isDeletingAccount) {
            event.preventDefault();
            return;
          }
          setIsDeleteDialogOpen(false);
          setDeletePassword("");
          setDeleteError("");
        }}
      >
        <form className="delete-account-form" onSubmit={deleteAccount}>
          <p className="eyebrow">FIÓKBEÁLLÍTÁSOK</p>
          <h2 id="delete-account-title">Fiók végleges törlése</h2>
          <p className="delete-account-warning">
            A törlés végleges, és nem lehet visszavonni. A fiókodhoz tartozó adatok és
            munkamenetek törlődnek.
          </p>

          <label htmlFor="delete-account-password">Add meg a jelszavad a megerősítéshez</label>
          <input
            id="delete-account-password"
            type="password"
            autoComplete="current-password"
            value={deletePassword}
            onChange={(event) => setDeletePassword(event.target.value)}
            required
            disabled={isDeletingAccount}
          />

          {deleteError && <p className="error-message" role="alert">{deleteError}</p>}

          <div className="delete-dialog-actions">
            <button
              className="cancel-delete-button"
              type="button"
              onClick={closeDeleteDialog}
              disabled={isDeletingAccount}
            >
              Mégse
            </button>
            <button className="confirm-delete-button" type="submit" disabled={isDeletingAccount}>
              {isDeletingAccount ? "Törlés…" : "Fiók végleges törlése"}
            </button>
          </div>
        </form>
      </dialog>
    </main>
  );
}
