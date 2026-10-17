/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "backend" reads modules/ingesta's API; anything else (including unset) keeps the demo fixtures. */
  readonly VITE_SERVICES_MODE?: "demo" | "backend";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
