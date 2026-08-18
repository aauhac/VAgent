/**
 * Client-only cleanup after Toss login unlink / revoked session.
 * Does not delete server analyses, audio, or payment records.
 */

import { clearUserIdentity } from './userIdentity';

export const SESSION_CLEARED_EVENT = 'vocalfb:session-cleared';

const STORAGE_PREFIXES = ['vocalfb_', 'vagent_'];

function revokeBlobUrl(value: string | null) {
  if (value && value.startsWith('blob:')) {
    try {
      URL.revokeObjectURL(value);
    } catch {
      /* ignore */
    }
  }
}

function removePrefixed(storage: Storage) {
  const keys: string[] = [];
  for (let i = 0; i < storage.length; i += 1) {
    const key = storage.key(i);
    if (key && STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix))) {
      keys.push(key);
    }
  }
  for (const key of keys) {
    if (key === 'vocalfb_last_blob') {
      try {
        revokeBlobUrl(storage.getItem(key));
      } catch {
        /* ignore */
      }
    }
    storage.removeItem(key);
  }
}

export function clearClientUserData(): void {
  clearUserIdentity();
  try {
    if (typeof sessionStorage !== 'undefined') removePrefixed(sessionStorage);
  } catch {
    /* ignore */
  }
  try {
    if (typeof localStorage !== 'undefined') removePrefixed(localStorage);
  } catch {
    /* ignore */
  }
}

export function handleUnauthorizedSession(): void {
  clearClientUserData();
  try {
    window.dispatchEvent(new Event(SESSION_CLEARED_EVENT));
  } catch {
    /* ignore */
  }
}
