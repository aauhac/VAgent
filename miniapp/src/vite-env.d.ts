/// <reference types="vite/client" />

declare module '*.md?raw' {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  /** Public VAgent backend origin. Required for production Toss builds. HTTPS only. */
  readonly VITE_API_BASE?: string;
  readonly VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
