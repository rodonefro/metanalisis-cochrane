/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DEV_BACKEND?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
