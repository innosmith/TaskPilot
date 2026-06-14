// CSS-Properties, die aus E-Mail-HTML entfernt werden, damit Outlook/Graph-Inline-Styles
// nicht die Theme-Farben (Light/Dark/Glass) überschreiben. Strukturelle Properties
// (padding, margin, font-weight, line-height, …) bleiben erhalten.
const STRIP_CSS_PROPS = new Set([
  'background',
  'background-color',
  'background-image',
  'font-family',
  'box-shadow',
  'color',
]);

/**
 * Entfernt Inline-Farben und -Hintergründe aus E-Mail-HTML (Microsoft Graph / Outlook),
 * damit der Text die Theme-Farbe erbt und im Dark Theme lesbar bleibt.
 *
 * Strippt `<style>`-Blöcke, `bgcolor`/`color`-Attribute sowie die in
 * {@link STRIP_CSS_PROPS} gelisteten CSS-Properties aus `style="…"`.
 */
export function sanitizeEmailHtml(html: string): string {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/\s*bgcolor="[^"]*"/gi, '')
    .replace(/\s*color="[^"]*"/gi, '')
    .replace(/style="([^"]*)"/gi, (_, css: string) => {
      const kept = css
        .split(';')
        .filter(p => {
          const name = p.split(':')[0]?.trim().toLowerCase() ?? '';
          return name && !STRIP_CSS_PROPS.has(name);
        })
        .join(';')
        .trim();
      return kept ? `style="${kept}"` : '';
    });
}
