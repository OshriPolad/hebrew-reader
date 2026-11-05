import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, clearToken, getToken } from "./api.js";
import Login from "./Login.jsx";
import AddArticle from "./AddArticle.jsx";
import Library from "./Library.jsx";
import Player from "./Player.jsx";
import UsageMeter from "./UsageMeter.jsx";

const POLL_MS = 3000;

export default function App() {
  const [authed, setAuthed] = useState(Boolean(getToken()));
  const [articles, setArticles] = useState([]);
  const [usage, setUsage] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [currentId, setCurrentId] = useState(null);
  const [error, setError] = useState("");
  const pollRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [list, u] = await Promise.all([api.list(), api.usage()]);
      setArticles(list);
      setUsage(u);
      setLoaded(true);
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        clearToken();
        setAuthed(false);
      } else {
        setError(e.message);
      }
    }
  }, []);

  useEffect(() => {
    if (authed) refresh();
  }, [authed, refresh]);

  // Poll only while something is being prepared.
  const processing = articles.some((a) => a.status === "processing");
  useEffect(() => {
    if (!processing) return;
    pollRef.current = setInterval(refresh, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [processing, refresh]);

  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;

  const current = articles.find((a) => a.id === currentId) || null;

  const patchLocal = (id, fields) =>
    setArticles((list) => list.map((a) => (a.id === id ? { ...a, ...fields } : a)));

  async function handleDelete(id) {
    await api.remove(id);
    if (id === currentId) setCurrentId(null);
    setArticles((list) => list.filter((a) => a.id !== id));
  }

  return (
    <div className={`shell ${current ? "has-player" : ""}`}>
      <header className="masthead">
        <h1>ההקראות שלי</h1>
        <UsageMeter usage={usage} />
      </header>

      <AddArticle onAdded={(a) => setArticles((list) => [a, ...list])} />

      {error && <p className="banner" role="alert">{error}</p>}

      <Library
        articles={articles}
        loaded={loaded}
        currentId={currentId}
        onPlay={setCurrentId}
        onDelete={handleDelete}
      />

      {current && current.status === "ready" && (
        <Player
          key={current.id}
          article={current}
          onProgress={(fields) => patchLocal(current.id, fields)}
          onClose={() => setCurrentId(null)}
        />
      )}
    </div>
  );
}
