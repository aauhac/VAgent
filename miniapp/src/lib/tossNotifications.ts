/**
 * Apps in Toss analysis-complete notification opt-in.
 * Client never sends the smart message itself.
 *
 * CTA visibility must not depend on template code or SDK capability.
 * Those are checked only when the user taps "완료 알림 받기".
 */

import { requestCompletionNotification } from '../api/client';

export type NotificationAgreementState =
  | 'IDLE'
  | 'REQUESTING'
  | 'AGREED'
  | 'REJECTED'
  | 'ERROR'
  | 'UNAVAILABLE';

const NOTIFY_ERROR = '알림 설정을 완료하지 못했어요. 다시 시도해 주세요.';
export const NOTIFY_UNAVAILABLE = '지금은 완료 알림을 사용할 수 없어요.';

function notifyLog(event: string) {
  try {
    console.info(`[NOTIFICATION] ${event}`);
  } catch {
    /* ignore */
  }
}

/** Build-time Vite env. Empty when not set in the miniapp build env. */
export function analysisCompleteTemplateCode(): string {
  return String(import.meta.env.VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE || '').trim();
}

/**
 * Whether the build includes a Console template code.
 * Do NOT use this to hide the Analyzing CTA — users must still see the offer.
 */
export function notificationFeatureAvailable(): boolean {
  return !!analysisCompleteTemplateCode();
}

export async function requestAnalysisCompleteAgreement(analysisId: string): Promise<{
  state: NotificationAgreementState;
  message?: string;
}> {
  const templateCode = analysisCompleteTemplateCode();
  if (!templateCode) {
    notifyLog('disabled template_missing');
    return { state: 'UNAVAILABLE', message: NOTIFY_UNAVAILABLE };
  }

  let mod: { requestNotificationAgreement?: Function };
  try {
    mod = await import('@apps-in-toss/web-framework');
  } catch {
    notifyLog('sdk_import_failed');
    return { state: 'UNAVAILABLE', message: NOTIFY_UNAVAILABLE };
  }
  const requestAgreement = mod.requestNotificationAgreement;
  if (typeof requestAgreement !== 'function') {
    notifyLog('sdk_fn_missing');
    return { state: 'UNAVAILABLE', message: NOTIFY_UNAVAILABLE };
  }

  return new Promise((resolve) => {
    let settled = false;
    let cleanup: (() => void) | undefined;
    const finish = (result: { state: NotificationAgreementState; message?: string }) => {
      if (settled) return;
      settled = true;
      try {
        cleanup?.();
      } catch {
        /* ignore */
      }
      resolve(result);
    };
    try {
      cleanup = requestAgreement({
        options: { templateCode },
        onEvent: (result: { type?: string }) => {
          const type = String(result?.type || '');
          if (type === 'agreementRejected') {
            finish({ state: 'REJECTED' });
            return;
          }
          if (type === 'newAgreement' || type === 'alreadyAgreed') {
            requestCompletionNotification(analysisId)
              .then(() => finish({ state: 'AGREED' }))
              .catch(() => finish({ state: 'ERROR', message: NOTIFY_ERROR }));
            return;
          }
          finish({ state: 'ERROR', message: NOTIFY_ERROR });
        },
        onError: () => {
          finish({ state: 'ERROR', message: NOTIFY_ERROR });
        },
      });
    } catch {
      finish({ state: 'UNAVAILABLE', message: NOTIFY_UNAVAILABLE });
    }
  });
}
