/// <reference types="vite/client" />

declare module '*.md?raw' {
  const content: string;
  export default content;
}

interface ImportMetaEnv {
  /** Public VAgent backend origin. Required for production Toss builds. HTTPS only. */
  readonly VITE_API_BASE?: string;
  readonly VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE?: string;
  /** Apps in Toss rewarded ad group ID for SONG_DETAIL. Empty until console issues ID. */
  readonly VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
