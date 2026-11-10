export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export function minutes(seconds) {
  const m = Math.max(1, Math.round((seconds || 0) / 60));
  return m === 1 ? "דקה אחת" : `${m} דקות`;
}

// Backend failure reasons -> plain Hebrew
export function failureText(error) {
  if (!error) return "ההקראה לא הצליחה.";
  if (error.includes("Monthly reading limit"))
    return "נגמרה מכסת ההקראה של החודש. היא תתחדש בתחילת החודש הבא.";
  if (error.includes("Scanned document is too long"))
    return "המסמך הסרוק ארוך מדי. אפשר עד 30 עמודים סרוקים.";
  if (error.includes("too long")) return "הכתבה ארוכה מדי להקראה אחת.";
  if (error.includes("No readable text found in the image")) return "לא נמצא טקסט בתמונה. נסו לצלם שוב, קרוב וחד יותר.";
  if (error.includes("No article text") || error.includes("No readable"))
    return "לא נמצא טקסט לקריאה בעמוד הזה.";
  if (error.includes("Monthly scanning limit"))
    return "נגמרה מכסת הסריקה של החודש. היא תתחדש בתחילת החודש הבא.";
  if (error.includes("OCR is not configured") || error.includes("no text layer"))
    return "זה מסמך סרוק, וקריאת סריקות עדיין לא הופעלה בשרת.";
  if (error.includes("scanning service")) return "שירות קריאת הסריקות לא זמין כרגע. נסו שוב מאוחר יותר.";
  if (error.includes("Old Word files")) return "קובצי Word ישנים (doc.) לא נתמכים בשרת.";
  if (error.includes("Could not open this Word file")) return "לא הצלחנו לפתוח את קובץ ה-Word.";
  if (error.includes("Unsupported file type")) return "סוג הקובץ לא נתמך.";
  if (error.includes("too large")) return "הקובץ גדול מדי.";
  if (error.includes("voice service")) return "שירות ההקראה לא זמין כרגע. נסו שוב מאוחר יותר.";
  if (error.includes("interrupted")) return "ההכנה נקטעה. הוסיפו את הכתבה שוב.";
  if (error.includes("returned an error") || error.includes("Could not"))
    return "לא הצלחנו לפתוח את הקישור.";
  return "ההקראה לא הצליחה.";
}

// ~150 spoken words per minute x ~6 characters per word
const CHARS_PER_MINUTE = 900;

export function listeningTimeLeft(chars) {
  const min = Math.floor(chars / CHARS_PER_MINUTE);
  if (min >= 120) return `כ-${Math.floor(min / 60)} שעות`;
  if (min >= 60) return "כשעה";
  if (min >= 2) return `כ-${min} דקות`;
  return "פחות מ-2 דקות";
}
