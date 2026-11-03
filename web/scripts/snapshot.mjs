// Save the live API response as the build fallback. Plan T26.
// Run: pnpm snapshot   (API_URL overrides the default API)
import { writeFile } from "node:fs/promises";

const api = (process.env.API_URL ?? "https://api.fatihiazmi.dev").replace(/\/$/, "");
const out = new URL("../src/data/projects.snapshot.json", import.meta.url);

const res = await fetch(`${api}/api/projects`, { signal: AbortSignal.timeout(10_000) });
if (!res.ok) {
  console.error(`error: GET ${api}/api/projects returned HTTP ${res.status}. Snapshot not written.`);
  process.exit(1);
}
const data = await res.json();
if (!Array.isArray(data.projects) || !Array.isArray(data.edges)) {
  console.error(`error: ${api}/api/projects has no projects or edges array. Snapshot not written.`);
  process.exit(1);
}
await writeFile(out, `${JSON.stringify(data, null, 2)}\n`);
console.log(`wrote ${data.projects.length} projects and ${data.edges.length} edges to ${out.pathname}`);
