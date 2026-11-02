import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { clock } from "./format.js";

const SPEEDS = [0.8, 1, 1.2, 1.5];
const SAVE_EVERY_MS = 10_000;

export default function Player({ article, onProgress, onClose }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(article.position_seconds || 0);
  const [duration, setDuration] = useState(article.duration_seconds || 0);
  const [speed, setSpeed] = useState(() => Number(localStorage.getItem("hr_speed")) || 1);

  const save = (extra = {}) => {
    const a = audioRef.current;
    if (!a) return;
    const fields = { position_seconds: Math.floor(a.currentTime), ...extra };
    onProgress(fields);
    api.update(article.id, fields).catch(() => {}); // best effort
  };

  // Start where she stopped last time (unless she already finished it).
  useEffect(() => {
    const a = audioRef.current;
    const start = () => {
      if (!article.listened && article.position_seconds > 0) a.currentTime = article.position_seconds;
      a.playbackRate = speed;
      a.play().catch(() => {}); // autoplay may be blocked; the button still works
    };
    a.addEventListener("loadedmetadata", start, { once: true });
    return () => a.removeEventListener("loadedmetadata", start);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Periodic save + save when the app goes to the background.
  useEffect(() => {
    const timer = setInterval(() => playing && save(), SAVE_EVERY_MS);
    const onHide = () => document.visibilityState === "hidden" && save();
    document.addEventListener("visibilitychange", onHide);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onHide);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  // Lock-screen / car controls.
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({ title: article.title, artist: "ההקראות שלי" });
    const a = audioRef.current;
    const handlers = {
      play: () => a.play(),
      pause: () => a.pause(),
      seekbackward: () => skip(-15),
      seekforward: () => skip(15),
      seekto: (d) => (a.currentTime = d.seekTime),
    };
    for (const [k, h] of Object.entries(handlers)) {
      try { navigator.mediaSession.setActionHandler(k, h); } catch { /* unsupported */ }
    }
    return () => {
      for (const k of Object.keys(handlers)) {
        try { navigator.mediaSession.setActionHandler(k, null); } catch { /* unsupported */ }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [article.id]);

  function skip(seconds) {
    const a = audioRef.current;
    a.currentTime = Math.min(Math.max(0, a.currentTime + seconds), a.duration || Infinity);
  }

  function toggle() {
    const a = audioRef.current;
    a.paused ? a.play() : a.pause();
  }

  function cycleSpeed() {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    audioRef.current.playbackRate = next;
    localStorage.setItem("hr_speed", String(next));
    setSpeed(next);
  }

  function close() {
    audioRef.current.pause();
    save();
    onClose();
  }

  return (
    <section className="player" aria-label="נגן">
      <audio
        ref={audioRef}
        src={api.audioUrl(article.id)}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => { setPlaying(false); save(); }}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onDurationChange={(e) => Number.isFinite(e.currentTarget.duration) && setDuration(e.currentTarget.duration)}
        onEnded={() => { setPlaying(false); save({ listened: true, position_seconds: 0 }); }}
      />

      <div className="player-head">
        <p className="player-title">{article.title}</p>
        <button className="ghost small" onClick={close} aria-label="סגירת הנגן">סגירה</button>
      </div>

      <input
        className="seek"
        type="range"
        min="0"
        max={duration || 0}
        step="1"
        value={Math.min(time, duration || 0)}
        onChange={(e) => (audioRef.current.currentTime = Number(e.target.value))}
        aria-label="מיקום בהקראה"
        dir="ltr"
      />
      <div className="times" dir="ltr">
        <span>{clock(time)}</span>
        <span>{clock(duration)}</span>
      </div>

      <div className="controls" dir="ltr">
        <button className="round" onClick={() => skip(-15)} aria-label="15 שניות אחורה">
          <span aria-hidden="true">−15</span>
        </button>
        <button className="play" onClick={toggle} aria-label={playing ? "השהיה" : "השמעה"}>
          {playing ? (
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" /></svg>
          )}
        </button>
        <button className="round" onClick={() => skip(15)} aria-label="15 שניות קדימה">
          <span aria-hidden="true">+15</span>
        </button>
      </div>

      <button className="speed" onClick={cycleSpeed} aria-label={`מהירות ${speed}`}>
        מהירות <bdi dir="ltr">{speed}×</bdi>
      </button>
    </section>
  );
}
