// @ts-check
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

// Static output for Cloudflare Pages. Spec section 2.
export default defineConfig({
  site: "https://fatihiazmi.dev",
  trailingSlash: "never",
  build: { format: "file" },
  vite: { plugins: [tailwindcss()] },
});
