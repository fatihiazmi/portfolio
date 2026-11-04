// @ts-check
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

// Static output for Cloudflare Pages. Spec section 2.
export default defineConfig({
  site: "https://fatihiazmi.dev",
  trailingSlash: "never",
  build: { format: "file" },
  vite: {
    plugins: [tailwindcss()],
    // three.js is one lazy chunk of about 530 KB raw, 135 KB gzipped. Spec 4.4 budgets 300 KB gzipped.
    build: { chunkSizeWarningLimit: 600 },
  },
});
