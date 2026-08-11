import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

type Props = {
  badge?: string;
  title: string;
  description: string;
  priceLabel?: string;
  bullets?: string[];
  ctaLabel: string;
  to?: string;
  onClick?: () => void;
  busy?: boolean;
  featured?: boolean;
  footer?: ReactNode;
};

/** Premium product block — not a plain primary button. */
export default function PremiumProductCard({
  badge,
  title,
  description,
  priceLabel,
  bullets = [],
  ctaLabel,
  to,
  onClick,
  busy,
  featured,
  footer,
}: Props) {
  const cta = to ? (
    <Link className="btn" to={to} style={{ width: '100%' }}>
      {ctaLabel}
    </Link>
  ) : (
    <button type="button" className="btn" style={{ width: '100%' }} disabled={busy} onClick={onClick}>
      {busy ? '준비 중…' : ctaLabel}
    </button>
  );

  return (
    <article className={`premium-card${featured ? ' is-featured' : ''}`}>
      <div className="premium-card-top">
        {badge ? <span className="premium-badge">{badge}</span> : null}
        {priceLabel ? <span className="premium-price">{priceLabel}</span> : null}
      </div>
      <h3 className="premium-title">{title}</h3>
      <p className="premium-desc">{description}</p>
      {bullets.length > 0 ? (
        <ul className="premium-bullets">
          {bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      ) : null}
      <div className="premium-cta">{cta}</div>
      {footer ? <div className="premium-footer">{footer}</div> : null}
    </article>
  );
}
