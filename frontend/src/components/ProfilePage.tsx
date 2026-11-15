import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import "./ProfilePage.css";
import { authenticatedFetch, clearAccessToken } from "../lib/session";

type Profile = {
  email: string;
};

type ConversionHistoryEntry = {
  id: number;
  source_filename: string;
  direction: "pdf-to-docx" | "docx-to-pdf";
  output_filename: string;
  output_size_bytes: number;
  created_at: string;
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("hu-HU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [conversionHistory, setConversionHistory] = useState<ConversionHistoryEntry[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [historyActionError, setHistoryActionError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [historyAction, setHistoryAction] = useState<"clear" | number | null>(null);
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

  useEffect(() => {
    if (!profile) return;

    let cancelled = false;
    authenticatedFetch("/api/conversions/history")
      .then(async (response) => {
        if (!response.ok) {
          const problem = (await response.json().catch(() => ({}))) as {
            detail?: unknown;
          };
          throw new Error(
            typeof problem.detail === "string"
              ? problem.detail
              : "Nem sikerült betölteni az előzményeket.",
          );
        }
        return (await response.json()) as ConversionHistoryEntry[];
      })
      .then((history) => {
        if (!cancelled) setConversionHistory(history);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHistoryError(
            error instanceof Error
              ? error.message
              : "Nem sikerült betölteni az előzményeket.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [profile]);

  async function downloadConversion(entry: ConversionHistoryEntry) {
    setDownloadingId(entry.id);
    setDownloadError("");

    try {
      const response = await authenticatedFetch(
        `/api/conversions/history/${entry.id}/download`,
      );
      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as {
          detail?: unknown;
        };
        throw new Error(
          typeof problem.detail === "string"
            ? problem.detail
            : "Nem sikerült letölteni a fájlt.",
        );
      }

      const objectUrl = URL.createObjectURL(await response.blob());
      const downloadLink = document.createElement("a");
      downloadLink.href = objectUrl;
      downloadLink.download = entry.output_filename;
      document.body.append(downloadLink);
      downloadLink.click();
      downloadLink.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error: unknown) {
      setDownloadError(
        error instanceof Error ? error.message : "Nem sikerült letölteni a fájlt.",
      );
    } finally {
      setDownloadingId(null);
    }
  }

  async function deleteHistoryEntry(entry: ConversionHistoryEntry) {
    setHistoryAction(entry.id);
    setHistoryActionError("");

    try {
      const response = await authenticatedFetch(
        `/api/conversions/history/${entry.id}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as {
          detail?: unknown;
        };
        throw new Error(
          typeof problem.detail === "string"
            ? problem.detail
            : "Nem sikerült törölni az előzményt.",
        );
      }

      setConversionHistory((history) => history.filter((item) => item.id !== entry.id));
    } catch (error: unknown) {
      setHistoryActionError(
        error instanceof Error ? error.message : "Nem sikerült törölni az előzményt.",
      );
    } finally {
      setHistoryAction(null);
    }
  }

  async function clearHistory() {
    if (conversionHistory.length === 0 || historyAction !== null) return;
    if (!window.confirm("Biztosan törlöd az összes előzményt és eredményfájlt?")) return;

    setHistoryAction("clear");
    setHistoryActionError("");

    try {
      const response = await authenticatedFetch("/api/conversions/history", {
        method: "DELETE",
      });
      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as {
          detail?: unknown;
        };
        throw new Error(
          typeof problem.detail === "string"
            ? problem.detail
            : "Nem sikerült törölni az előzményeket.",
        );
      }

      setConversionHistory([]);
    } catch (error: unknown) {
      setHistoryActionError(
        error instanceof Error ? error.message : "Nem sikerült törölni az előzményeket.",
      );
    } finally {
      setHistoryAction(null);
    }
  }

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
          <div className="history-heading">
            <h2 id="history-heading">Előzmények</h2>
            {!isLoadingHistory && !historyError && conversionHistory.length > 0 && (
              <button
                className="clear-history-button"
                type="button"
                onClick={() => void clearHistory()}
                disabled={historyAction !== null || downloadingId !== null}
              >
                {historyAction === "clear" ? "Törlés…" : "Összes törlése"}
              </button>
            )}
          </div>
          {isLoadingHistory ? (
            <p className="history-empty" role="status">Előzmények betöltése…</p>
          ) : historyError ? (
            <p className="history-error" role="alert">{historyError}</p>
          ) : conversionHistory.length === 0 ? (
            <p className="history-empty">Még nincs mentett konverzió.</p>
          ) : (
            <ul className="history-list">
              {conversionHistory.map((entry) => (
                <li className="history-entry" key={entry.id}>
                  <div className="history-entry-details">
                    <strong className="history-entry-filename">{entry.source_filename}</strong>
                    <span>
                      {entry.direction === "pdf-to-docx" ? "PDF → DOCX" : "DOCX → PDF"}
                    </span>
                    <span>
                      {formatDate(entry.created_at)} · {formatFileSize(entry.output_size_bytes)}
                    </span>
                  </div>
                  <div className="history-entry-actions">
                    <button
                      className="history-download-button"
                      type="button"
                      aria-label={`Letöltés: ${entry.output_filename}`}
                      onClick={() => void downloadConversion(entry)}
                      disabled={downloadingId !== null || historyAction !== null}
                    >
                      {downloadingId === entry.id ? "Letöltés…" : "Letöltés"}
                    </button>
                    <button
                      className="history-delete-button"
                      type="button"
                      aria-label={`Előzmény törlése: ${entry.source_filename}`}
                      title="Előzmény törlése"
                      onClick={() => void deleteHistoryEntry(entry)}
                      disabled={historyAction !== null || downloadingId !== null}
                    >
                      {historyAction === entry.id ? "…" : "×"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {historyActionError && (
            <p className="history-error" role="alert">{historyActionError}</p>
          )}
          {downloadError && <p className="history-error" role="alert">{downloadError}</p>}
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
