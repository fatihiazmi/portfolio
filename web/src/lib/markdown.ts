/**
 * Build-time markdown for case study fields (`problem_md`, `built_md`, and the rest).
 *
 * The owner writes these fields in the admin. The renderer still treats them as untrusted:
 * - Raw HTML is dropped.
 * - Links keep only `https:`, `http:`, `mailto:`, site-relative, and `#` targets.
 *   Any other link renders as its plain text.
 * - Images keep only `https:` sources. Any other image renders as its alt text.
 */
import { Marked } from "marked";

const SAFE_LINK = /^(https?:|mailto:|\/(?!\/)|#)/i;
const SAFE_IMAGE = /^https:/i;

const marked = new Marked({
  gfm: true,
  renderer: {
    html() {
      return "";
    },
    link({ href, tokens }) {
      // `false` hands the token back to the default renderer.
      return SAFE_LINK.test(href) ? false : this.parser.parseInline(tokens);
    },
    image({ href, text }) {
      return SAFE_IMAGE.test(href) ? false : escapeHtml(text);
    },
  },
});

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** Markdown to HTML. Pass the result to `set:html`. */
export function renderMarkdown(source: string): string {
  return marked.parse(source, { async: false });
}
