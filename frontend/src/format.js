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
  if (error.includes("too long")) return "הכתבה ארוכה מדי להקראה אחת.";
  if (error.includes("No article text") || error.includes("No readable"))
    return "לא נמצא טקסט לקריאה בעמוד הזה.";
  if (error.includes("no text layer")) return "זה PDF סרוק (תמונה). אפשר להקריא רק PDF עם טקסט.";
  if (error.includes("voice service")) return "שירות ההקראה לא זמין כרגע. נסו שוב מאוחר יותר.";
  if (error.includes("interrupted")) return "ההכנה נקטעה. הוסיפו את הכתבה שוב.";
  if (error.includes("returned an error") || error.includes("Could not"))
    return "לא הצלחנו לפתוח את הקישור.";
  return "ההקראה לא הצליחה.";
}
