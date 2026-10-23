export const EMAIL_FONT = 'Helvetica, sans-serif';

export const escapeEmailText = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[character]));

// Apply the email-safe font to server-built HTML fragments, including nested table cells.
export function fontEmailHtml(html) {
  return html.replace(/<(table|td|th|p|div|span|a|h[1-6]|strong|em)\b([^>]*)>/gi, (match, tag, attributes) => {
    if (/font-family\s*:/i.test(attributes)) return match;
    const styled = /\bstyle="/i.test(attributes)
      ? attributes.replace(/\bstyle="/i, `style="font-family:${EMAIL_FONT};`)
      : ` style="font-family:${EMAIL_FONT};"${attributes}`;
    return `<${tag}${styled}>`;
  });
}