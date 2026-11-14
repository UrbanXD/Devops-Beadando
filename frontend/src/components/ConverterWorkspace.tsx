import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import "./ConverterWorkspace.css";

type ConversionDirection = "pdf-to-docx" | "docx-to-pdf";

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

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) return;

    setStatusMessage(
      "A konverziós API még nincs bekötve. A fájl egyelőre nem kerül feltöltésre.",
    );
  }

  return (
    <form className="converter-form" onSubmit={handleSubmit}>
      <fieldset className="conversion-direction">
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
          accept={direction === "pdf-to-docx" ? ".pdf,application/pdf" : ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
          onChange={handleFileChange}
        />
        <span className="converter-upload-icon" aria-hidden="true">↑</span>
        <span className="converter-dropzone-title">Húzd ide a fájlt, vagy tallózd be</span>
        <span className="converter-dropzone-hint">
          Ehhez az irányhoz {requiredExtension(direction)} fájl választható.
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
          >
            Eltávolítás
          </button>
        </div>
      )}

      {errorMessage && <p className="error-message" role="alert">{errorMessage}</p>}

      <button className="primary-button converter-submit" type="submit" disabled={!selectedFile}>
        Konvertálás
      </button>

      {statusMessage ? (
        <p className="converter-status" role="status">{statusMessage}</p>
      ) : (
        <p className="converter-note">
          A fájl előkészítése működik; a tényleges konvertálás bekötése fejlesztés alatt áll.
        </p>
      )}
    </form>
  );
}
