// Shapes of the admin JSON API. Source of truth: `api/src/portfolio_api/admin*.py`.

export type ProjectKind = "client" | "personal";
export type LeadKind = "freelance" | "hiring" | "other";
export type LeadStatus = "new" | "replied" | "closed";

export interface AdminImage {
  id: number;
  project_id: number;
  r2_key: string;
  url: string;
  alt: string;
  caption: string | null;
  sort_order: number;
  scrubbed: boolean;
}

export interface AdminProject {
  id: number;
  slug: string;
  title: string;
  client: string | null;
  kind: ProjectKind;
  year: number | null;
  summary: string;
  problem_md: string | null;
  built_md: string | null;
  decisions_md: string | null;
  outcome_md: string | null;
  stack: string[];
  repo_url: string | null;
  diagram_key: string | null;
  diagram_url: string | null;
  map_x: number | null;
  map_z: number | null;
  sort_order: number;
  published: boolean;
  updated_at: string;
  images: AdminImage[];
}

/** The fields the edit form sends. `null` clears a nullable field. The map editor owns `map_x` and `map_z`. */
export type ProjectInput = Pick<
  AdminProject,
  | "slug"
  | "title"
  | "client"
  | "kind"
  | "year"
  | "summary"
  | "problem_md"
  | "built_md"
  | "decisions_md"
  | "outcome_md"
  | "stack"
  | "repo_url"
  | "published"
>;

export interface AdminEdge {
  from_id: number;
  to_id: number;
  label: string | null;
}

/** Node position from the map editor. `null` on both takes the project off the map. */
export interface MapPosition {
  map_x: number | null;
  map_z: number | null;
}

export interface AdminProjectList {
  projects: AdminProject[];
  edges: AdminEdge[];
}

export interface Publish {
  id: number;
  created_at: string;
  ok: boolean;
  deploy_id: string | null;
  error: string | null;
}

export interface Summary {
  leads: { new: number; total: number };
  projects: { total: number; published: number };
  blocking_images: number;
  last_publish: Publish | null;
  last_backup_at: string | null;
}

export interface Lead {
  id: number;
  created_at: string;
  name: string;
  email: string;
  company: string | null;
  kind: LeadKind;
  budget: string | null;
  message: string;
  status: LeadStatus;
}

export interface LeadList {
  leads: Lead[];
  total: number;
}

export interface ImagePatch {
  alt?: string;
  caption?: string;
  sort_order?: number;
  scrubbed?: boolean;
}
