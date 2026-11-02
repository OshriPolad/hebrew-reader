import { useState } from "react";
import { clock, failureText, minutes } from "./format.js";

function Status({ a }) {
  if (a.status === "processing")
    return <span className="status processing">מכין הקראה…</span>;
  if (a.status === "failed")
    return <span className="status failed">{failureText(a.error)}</span>;
  if (a.listened) return <span className="status">{minutes(a.duration_seconds)}, הושמע עד הסוף</span>;
  if (a.position_seconds > 5)
    return (
      <span className="status">
        {minutes(a.duration_seconds)}, נעצר ב-<bdi dir="ltr">{clock(a.position_seconds)}</bdi>
      </span>
    );
  return <span className="status">{minutes(a.duration_seconds)}, חדש</span>;
}

export default function Library({ articles, loaded, currentId, onPlay, onDelete }) {
  const [confirmId, setConfirmId] = useState(null);

  if (!loaded) return <p className="hint">טוען…</p>;
  if (!articles.length)
    return (
      <p className="empty">
        עדיין אין כאן כלום. הדביקו קישור לכתבה או בחרו קובץ PDF, וההקראה תופיע כאן.
      </p>
    );

  return (
    <ul className="library">
      {articles.map((a) => {
        const playable = a.status === "ready";
        return (
          <li key={a.id} className={`item ${a.id === currentId ? "current" : ""} ${a.status}`}>
            <button
              className="item-main"
              disabled={!playable}
              onClick={() => onPlay(a.id)}
              aria-label={playable ? `השמעה: ${a.title}` : a.title}
            >
              <span className="item-title">{a.title}</span>
              <Status a={a} />
            </button>

            {confirmId === a.id ? (
              <div className="confirm">
                <button className="danger" onClick={() => onDelete(a.id)}>מחיקה</button>
                <button className="ghost" onClick={() => setConfirmId(null)}>ביטול</button>
              </div>
            ) : (
              a.status !== "processing" && (
                <button className="ghost small" onClick={() => setConfirmId(a.id)} aria-label={`מחיקת ${a.title}`}>
                  מחיקה
                </button>
              )
            )}
          </li>
        );
      })}
    </ul>
  );
}
