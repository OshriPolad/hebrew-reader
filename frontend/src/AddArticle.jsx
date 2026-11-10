import { useRef, useState } from "react";
import { api } from "./api.js";

const ACCEPT = [
  "application/pdf", ".pdf",
  ".docx", ".doc", ".rtf", ".odt",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "image/*", ".heic",
].join(",");

export default function AddArticle({ onAdded, ocrEnabled }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);
  const cameraRef = useRef(null);

  async function run(promise) {
    setBusy(true);
    setError("");
    try {
      onAdded(await promise);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submitUrl(e) {
    e.preventDefault();
    if (await run(api.addUrl(url.trim()))) setUrl("");
  }

  async function pickFile(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow picking the same file again
    if (file) await run(api.addFile(file));
  }

  async function pasteFromClipboard() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setUrl(text.trim());
    } catch {
      /* clipboard permission denied: user can still paste manually */
    }
  }

  return (
    <section className="add" aria-label="הוספת כתבה">
      <form onSubmit={submitUrl} className="add-url">
        <label htmlFor="url">קישור לכתבה</label>
        <div className="url-row">
          <input
            id="url"
            type="url"
            inputMode="url"
            dir="ltr"
            placeholder="https://"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          {!url && navigator.clipboard?.readText && (
            <button type="button" className="ghost" onClick={pasteFromClipboard}>
              הדבקה
            </button>
          )}
        </div>
        <button className="primary" disabled={busy || !url.trim()}>
          הקראת הקישור
        </button>
      </form>

      <div className="or" aria-hidden="true">או</div>

      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={pickFile}
      />
      <button className="secondary" disabled={busy} onClick={() => fileRef.current.click()}>
        בחירת קובץ
      </button>
      <p className="hint file-types">קובצי PDF, Word ותמונות, גם סרוקים</p>

      {ocrEnabled && (
        <>
          {/* Opens the camera on phones: photograph a printed page and hear it */}
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={pickFile} />
          <button className="secondary camera" disabled={busy} onClick={() => cameraRef.current.click()}>
            צילום דף מודפס
          </button>
        </>
      )}

      {busy && <p className="hint" role="status">שולח…</p>}
      {error && <p className="field-error" role="alert">{error}</p>}
    </section>
  );
}
