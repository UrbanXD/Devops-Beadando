import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import "./ConverterWorkspace.css";
import { authenticatedFetch } from "../lib/session";

type ConversionDirection = "pdf-to-docx" | "docx-to-pdf";
const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024;

function requiredExtension(direction: ConversionDirection): string {
  return direction === "pdf-to-docx" ? ".pdf" : ".docx";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ConverterWorkspace() {
  const [direction, setDirection] = useState<ConversionDirection>("pdf-to-docx");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function chooseFile(file: File | undefined) {
    if (!file) return;

    setStatusMessage("");
    if (!file.name.toLowerCase().endsWith(requiredExtension(direction))) {
      setSelectedFile(null);
      setErrorMessage(`Ehhez az irányhoz ${requiredExtension(direction)} fájl szükséges.`);
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setSelectedFile(null);
      setErrorMessage("A fájl legfeljebb 25 MB lehet.");
      return;
    }

    setSelectedFile(file);
    setErrorMessage("");
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.currentTarget.files?.[0]);
    event.currentTarget.value = "";
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (isConverting) return;
    chooseFile(event.dataTransfer.files[0]);
  }

  function changeDirection(nextDirection: ConversionDirection) {
    setDirection(nextDirection);
    setStatusMessage("");

    if (selectedFile && !selectedFile.name.toLowerCase().endsWith(requiredExtension(nextDirection))) {
      setSelectedFile(null);
      setErrorMessage(`Ehhez az irányhoz ${requiredExtension(nextDirection)} fájl szükséges.`);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setErrorMessage("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile || isConverting) return;

    setErrorMessage("");
    setStatusMessage("A dokumentum konvertálása folyamatban van…");
    setIsConverting(true);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await authenticatedFetch(`/api/conversions/${direction}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as {
          detail?: string | Array<{ msg?: string }>;
        };
        const message =
          typeof problem.detail === "string"
            ? problem.detail
            : problem.detail?.[0]?.msg;
        throw new Error(message || "Nem sikerült konvertálni a fájlt. Próbáld újra.");
      }

      const objectUrl = URL.createObjectURL(await response.blob());
      const downloadLink = document.createElement("a");
      downloadLink.href = objectUrl;
      const sourceStem = selectedFile.name.replace(/\.[^/.]+$/, "") || "document";
      const outputExtension = direction === "pdf-to-docx" ? ".docx" : ".pdf";
      downloadLink.download = `${sourceStem}${outputExtension}`;
      document.body.append(downloadLink);
      downloadLink.click();
      downloadLink.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);

      setStatusMessage("A konvertált fájl letöltése elindult.");
    } catch (error: unknown) {
      setStatusMessage("");
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Nem sikerült konvertálni a fájlt. Próbáld újra.",
      );
    } finally {
      setIsConverting(false);
    }
  }

  return (
    <form className="converter-form" onSubmit={handleSubmit}>
      <fieldset className="conversion-direction" disabled={isConverting}>
        <legend>Konverzió iránya</legend>
        <div className="conversion-direction-options">
          <label className={`conversion-option ${direction === "pdf-to-docx" ? "active" : ""}`}>
            <input
              type="radio"
              name="conversion-direction"
              value="pdf-to-docx"
              checked={direction === "pdf-to-docx"}
              onChange={() => changeDirection("pdf-to-docx")}
            />
            <span className="conversion-option-format">PDF</span>
            <span className="conversion-option-arrow" aria-hidden="true">→</span>
            <span className="conversion-option-format">DOCX</span>
          </label>

          <label className={`conversion-option ${direction === "docx-to-pdf" ? "active" : ""}`}>
            <input
              type="radio"
              name="conversion-direction"
              value="docx-to-pdf"
              checked={direction === "docx-to-pdf"}
              onChange={() => changeDirection("docx-to-pdf")}
            />
            <span className="conversion-option-format">DOCX</span>
            <span className="conversion-option-arrow" aria-hidden="true">→</span>
            <span className="conversion-option-format">PDF</span>
          </label>
        </div>
      </fieldset>

      <label
        className={`converter-dropzone ${isDragging ? "dragging" : ""}`}
        htmlFor="converter-file"
        onDragOver={(event) => {
          event.preventDefault();
          if (isConverting) return;
          setIsDragging(true);
        }}
        onDragLeave={(event) => {
          const relatedTarget = event.relatedTarget;
          if (relatedTarget instanceof Node && event.currentTarget.contains(relatedTarget)) return;
          setIsDragging(false);
        }}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          className="converter-file-input"
          id="converter-file"
          type="file"
          accept={
            direction === "pdf-to-docx"
              ? ".pdf,application/pdf"
              : ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          }
          disabled={isConverting}
          onChange={handleFileChange}
        />
        <span className="converter-upload-icon" aria-hidden="true">↑</span>
        <span className="converter-dropzone-title">Húzd ide a fájlt, vagy tallózd be</span>
        <span className="converter-dropzone-hint">
          Ehhez az irányhoz {requiredExtension(direction)} fájl választható,
          legfeljebb 25 MB méretben.
        </span>
        <span className="converter-file-picker">Fájl kiválasztása</span>
      </label>

      {selectedFile && (
        <div className="selected-file" aria-label="Kiválasztott fájl">
          <span className="selected-file-icon" aria-hidden="true">
            {direction === "pdf-to-docx" ? "PDF" : "DOCX"}
          </span>
          <span className="selected-file-details">
            <span className="selected-file-name">{selectedFile.name}</span>
            <span className="selected-file-size">{formatFileSize(selectedFile.size)}</span>
          </span>
          <button
            className="remove-file-button"
            type="button"
            onClick={() => {
              setSelectedFile(null);
              setStatusMessage("");
              if (fileInputRef.current) fileInputRef.current.value = "";
            }}
            disabled={isConverting}
          >
            Eltávolítás
          </button>
        </div>
      )}

      {errorMessage && <p className="error-message" role="alert">{errorMessage}</p>}

      <button
        className="primary-button converter-submit"
        type="submit"
        disabled={!selectedFile || isConverting}
      >
        {isConverting ? "Konvertálás…" : "Konvertálás"}
      </button>

      {statusMessage ? (
        <p className="converter-status" role="status">{statusMessage}</p>
      ) : (
        <p className="converter-note">
          Bejelentkezés nélkül is használható. Az átalakított fájl letöltése
          automatikusan elindul.
        </p>
      )}
    </form>
  );
}
