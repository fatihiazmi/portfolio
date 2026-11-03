/** Site-wide constants shared by pages and components. */

/** Public address for the `mailto:` fallback when the contact API is down. Spec section 2.2. */
export const CONTACT_EMAIL = "fatihiazmi@gmail.com";

/** Base URL of the FastAPI service. Build-time `API_URL` overrides it. */
export const API_URL = (import.meta.env.API_URL ?? "https://api.fatihiazmi.dev").replace(/\/$/, "");

/** Cloudflare test site key. Every check passes. Dev builds only. */
const TURNSTILE_TEST_SITE_KEY = "1x00000000000000000000AA";

/**
 * Turnstile site key for the contact form.
 * Production reads `PUBLIC_TURNSTILE_SITE_KEY`. Without it, the form runs in `mailto:` mode.
 */
export const TURNSTILE_SITE_KEY: string | undefined =
  import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ||
  (import.meta.env.DEV ? TURNSTILE_TEST_SITE_KEY : undefined);
