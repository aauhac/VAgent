/**
 * Shared sub-page back target: in-app history when we arrived via PUSH/REPLACE,
 * otherwise Home. Never follow external history.
 */

export function resolveSubPageBack(
  navigationType?: 'POP' | 'PUSH' | 'REPLACE',
): { mode: 'history' } | { mode: 'home' } {
  if (navigationType === 'PUSH' || navigationType === 'REPLACE') {
    return { mode: 'history' };
  }
  return { mode: 'home' };
}
