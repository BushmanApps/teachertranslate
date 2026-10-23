// Returns an ISO 8601 timestamp in the Australia/Sydney (Canberra) timezone,
// e.g. "2026-10-11T21:01:00.000+11:00" — same ISO 8601 format as the
// platform's created_date, but carrying the Sydney timezone offset so the
// dashboard shows Canberra local time instead of UTC.
export function sydneyTimestamp(date = new Date()) {
  const sParts = new Intl.DateTimeFormat("en-AU", {
    timeZone: "Australia/Sydney",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const uParts = new Intl.DateTimeFormat("en-AU", {
    timeZone: "UTC",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const p = {};
  const u = {};
  for (const part of sParts) p[part.type] = part.value;
  for (const part of uParts) u[part.type] = part.value;

  const sydneyMs = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  const utcMs = Date.UTC(+u.year, +u.month - 1, +u.day, +u.hour, +u.minute, +u.second);
  const offsetMin = Math.round((sydneyMs - utcMs) / 60000);
  const sign = offsetMin >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMin);
  const offset = `${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`;

  const hour = p.hour === "24" ? "00" : p.hour;
  return `${p.year}-${p.month}-${p.day}T${hour}:${p.minute}:${p.second}.000${offset}`;
}