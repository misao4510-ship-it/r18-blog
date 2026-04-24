/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly FANZA_AF_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
