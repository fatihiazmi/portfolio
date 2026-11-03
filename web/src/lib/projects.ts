/**
 * Build-time project data. Spec section 2.1 and 2.2.
 *
 * Fetches `${API_URL}/api/projects` once per build. On any error (network,
 * timeout, non-200, or a response that fails the schema), the build uses
 * `src/data/projects.snapshot.json` and logs a warning. A homelab outage
 * never breaks a Pages build.
 */
import { z } from "astro/zod";
import snapshot from "../data/projects.snapshot.json";
import { API_URL } from "./site";

const TIMEOUT_MS = 10_000;

const image = z.object({
  url: z.string(),
  alt: z.string(),
  caption: z.string().nullable(),
});

const project = z.object({
  slug: z.string(),
  title: z.string(),
  client: z.string().nullable(),
  kind: z.enum(["client", "personal"]),
  year: z.number().int().nullable(),
  summary: z.string(),
  problem_md: z.string().nullable(),
  built_md: z.string().nullable(),
  decisions_md: z.string().nullable(),
  outcome_md: z.string().nullable(),
  stack: z.array(z.string()),
  repo_url: z.string().nullable(),
  diagram_url: z.string().nullable(),
  map_x: z.number().nullable(),
  map_z: z.number().nullable(),
  updated_at: z.string(),
  images: z.array(image),
});

const edge = z.object({
  source: z.string(),
  target: z.string(),
  label: z.string().nullable(),
});

export const projectList = z.object({
  projects: z.array(project),
  edges: z.array(edge),
});

export type Project = z.infer<typeof project>;
export type Edge = z.infer<typeof edge>;
export type ProjectData = z.infer<typeof projectList> & { source: "api" | "snapshot" };

let cached: Promise<ProjectData> | undefined;

/** Project data for this build. Every page shares one fetch. */
export function getProjects(): Promise<ProjectData> {
  cached ??= load();
  return cached;
}

async function load(): Promise<ProjectData> {
  const url = `${API_URL}/api/projects`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const parsed = projectList.safeParse(await res.json());
    if (!parsed.success) {
      const first = parsed.error.issues[0];
      throw new Error(`response does not match the schema at ${first?.path.join(".") || "root"}`);
    }
    const data = parsed.data;
    console.info(`[projects] ${data.projects.length} projects from ${url}`);
    return { ...data, source: "api" };
  } catch (err) {
    const data = projectList.parse(snapshot);
    const reason = err instanceof Error ? err.message : String(err);
    console.warn(
      `[projects] fetch ${url} failed: ${reason}. Using projects.snapshot.json` +
        ` (${data.projects.length} projects).`,
    );
    return { ...data, source: "snapshot" };
  }
}
