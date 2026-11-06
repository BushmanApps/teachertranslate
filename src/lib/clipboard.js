export async function copyText(value) {
  const text = String(value ?? "");
  if (!text) throw new Error("Nothing to copy");

  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {}
  }

  if (typeof document === "undefined") throw new Error("Clipboard is unavailable");

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  const copied = document.execCommand("copy");
  textarea.remove();

  if (!copied) throw new Error("Clipboard is unavailable");
}
