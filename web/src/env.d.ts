interface ImportMetaEnv {
  /** Build-time API base URL. Default: https://api.fatihiazmi.dev */
  readonly API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
