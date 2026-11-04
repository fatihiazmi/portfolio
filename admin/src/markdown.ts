/**
 * Markdown preview for the case study fields.
 *
 * Same rules as the site renderer in `web/src/lib/markdown.ts`, so the preview matches
 * the published page. Change both files together.
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

/** Markdown to HTML for `v-html`. */
export function renderMarkdown(source: string): string {
  return marked.parse(source, { async: false });
}
