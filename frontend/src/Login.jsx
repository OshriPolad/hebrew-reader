import { useState } from "react";
import { api, clearToken, setToken } from "./api.js";

export default function Login({ onSuccess }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setToken(code.trim());
    try {
      await api.list(); // any authed call verifies the code
      onSuccess();
    } catch (err) {
      clearToken();
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <h1>ההקראות שלי</h1>
      <p className="lede">כתבות ומסמכים, מוקראים מילה במילה.</p>
      <form onSubmit={submit}>
        <label htmlFor="code">קוד כניסה</label>
        <input
          id="code"
          type="password"
          autoComplete="current-password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          dir="ltr"
          required
        />
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className="primary" disabled={busy || !code.trim()}>
          {busy ? "בודק…" : "כניסה"}
        </button>
      </form>
      <p className="hint">את הקוד מזינים פעם אחת בלבד במכשיר הזה.</p>
    </main>
  );
}
