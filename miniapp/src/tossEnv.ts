/** Safe runtime helpers — never crash outside Toss WebView. */

export function isTossEnv(): boolean {
  try {
    const w = window as any;
    return Boolean(
      w?.AppsInToss
      || w?.granite
      || /Toss/i.test(navigator.userAgent)
      || /intoss/i.test(window.location.href),
    );
  } catch {
    return false;
  }
}
