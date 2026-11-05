interface ImportMetaEnv {
  /** Build-time API base URL. Default: https://api.fatihiazmi.dev */
  readonly API_URL?: string;
  /** Turnstile site key for the contact form. Public value. Unset in production: `mailto:` mode. */
  readonly PUBLIC_TURNSTILE_SITE_KEY?: string;
  /** Commit SHA. Cloudflare Pages sets it on every build. */
  readonly CF_PAGES_COMMIT_SHA?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
