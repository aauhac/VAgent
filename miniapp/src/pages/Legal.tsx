import LegalMarkdown from '../legal/LegalMarkdown';
import termsMd from '../legal/TERMS_OF_SERVICE.ko.md?raw';
import privacyMd from '../legal/PRIVACY_POLICY.ko.md?raw';
import consentMd from '../legal/PRIVACY_COLLECTION_CONSENT.ko.md?raw';

const DOCS = {
  terms: { title: '이용약관', source: termsMd },
  privacy: { title: '개인정보처리방침', source: privacyMd },
  'privacy-consent': { title: '수집·이용 동의', source: consentMd },
} as const;

type LegalSlug = keyof typeof DOCS;

export default function LegalPage({ slug }: { slug: LegalSlug }) {
  const doc = DOCS[slug];
  return (
    <main className="legal-page" data-testid={`legal-${slug}`} aria-label={doc.title}>
      <LegalMarkdown source={doc.source} />
    </main>
  );
}

export function LegalTerms() {
  return <LegalPage slug="terms" />;
}

export function LegalPrivacy() {
  return <LegalPage slug="privacy" />;
}

export function LegalPrivacyConsent() {
  return <LegalPage slug="privacy-consent" />;
}
