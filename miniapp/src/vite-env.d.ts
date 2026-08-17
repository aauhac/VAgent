/// <reference types="vite/client" />

declare module '*.md?raw' {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  /** Public VAgent backend origin. Required for production Toss builds. HTTPS only. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
