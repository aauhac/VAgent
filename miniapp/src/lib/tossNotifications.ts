/**
 * Apps in Toss analysis-complete notification opt-in.
 * Client never sends the smart message itself.
 *
 * Production CTA is shown only when a build-time template code is configured.
 * Template / SDK / backend failures must not look like analysis failure.
 */

import { requestCompletionNotification } from '../api/client';

export type NotificationAgreementState =
  | 'IDLE'
  | 'REQUESTING'
  | 'AGREED'
  | 'REJECTED'
  | 'ERROR'
  | 'UNAVAILABLE';

const NOTIFY_ERROR = '알림 설정을 완료하지 못했어요. 분석은 계속 진행돼요.';
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

/** Production CTA gate: hide offer when template code is not configured. */
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
            notifyLog('agreementRejected');
            finish({ state: 'REJECTED' });
            return;
          }
          if (type === 'newAgreement' || type === 'alreadyAgreed') {
            notifyLog(type);
            requestCompletionNotification(analysisId)
              .then(() => finish({ state: 'AGREED' }))
              .catch(() => {
                notifyLog('backend_request_failed');
                finish({ state: 'ERROR', message: NOTIFY_ERROR });
              });
            return;
          }
          notifyLog(type ? `unknown_event:${type}` : 'unknown_event');
          finish({ state: 'ERROR', message: NOTIFY_ERROR });
        },
        onError: () => {
          notifyLog('sdk_error');
          finish({ state: 'ERROR', message: NOTIFY_ERROR });
        },
      });
    } catch {
      notifyLog('sdk_error');
      finish({ state: 'UNAVAILABLE', message: NOTIFY_UNAVAILABLE });
    }
  });
}
