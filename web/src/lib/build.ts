/**
 * Build facts for the `/stack` page. Spec section 7: "Deployed version: Git SHA baked in at build".
 * Cloudflare Pages sets `CF_PAGES_COMMIT_SHA` on every build. Local builds show `dev`.
 */

/** Short commit SHA of this build, 7 characters, or `dev`. */
export const BUILD_SHA = (import.meta.env.CF_PAGES_COMMIT_SHA || "dev").slice(0, 7);

/** Build time, ISO 8601 UTC. */
export const BUILD_AT = new Date().toISOString();
