import { listeningTimeLeft } from "./format.js";

// How much reading is left this month (Azure free tier), in words she understands: time.
export default function UsageMeter({ usage }) {
  if (!usage) return null;
  const { used_chars, quota_chars, remaining_chars, ocr_enabled, ocr_pages_used, ocr_pages_quota } = usage;
  const pagesLeft = Math.max(0, (ocr_pages_quota || 0) - (ocr_pages_used || 0));
  const usedPct = Math.min(100, Math.round((used_chars / quota_chars) * 100));
  const low = remaining_chars < quota_chars * 0.15;
  const empty = remaining_chars <= 0;

  return (
    <div className={`usage ${low ? "low" : ""}`}>
      <p className="usage-text">
        {empty
          ? "מכסת ההקראה של החודש נוצלה. היא תתחדש בתחילת החודש הבא."
          : `נותרו החודש ${listeningTimeLeft(remaining_chars)} הקראה`}
      </p>
      <div
        className="usage-bar"
        role="meter"
        aria-label="ניצול מכסת ההקראה החודשית"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={usedPct}
      >
        <span style={{ width: `${usedPct}%` }} />
      </div>
      {ocr_enabled && ocr_pages_used > 0 && (
        <p className="usage-sub">נותרו החודש {pagesLeft} עמודים סרוקים</p>
      )}
    </div>
  );
}
