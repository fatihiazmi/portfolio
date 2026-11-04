import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";

// Dev: `api/scripts/dev_admin.py` writes `ADMIN_DEV_JWT` to `.env.development.local`.
// The proxy adds it to every `/api` request, so the API's real Access check passes.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "ADMIN_DEV_");
  const jwt = env.ADMIN_DEV_JWT ?? "";
  return {
    base: "/admin/",
    plugins: [vue()],
    build: {
      outDir: fileURLToPath(new URL("../api/static/admin", import.meta.url)),
      emptyOutDir: true,
    },
    server: {
      proxy: {
        "/api": {
          target: env.ADMIN_DEV_API ?? "http://127.0.0.1:8000",
          headers: jwt ? { "Cf-Access-Jwt-Assertion": jwt } : {},
        },
      },
    },
  };
});
