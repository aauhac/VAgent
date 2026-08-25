import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

type BaseProps = {
  badge?: string;
  title: string;
  description: string;
  priceLabel?: string;
  bullets?: string[];
  ctaLabel?: string;
  to?: string;
  onClick?: () => void;
  busy?: boolean;
  footer?: ReactNode;
  disabled?: boolean;
  retryable?: boolean;
  onRetry?: () => void;
};

/**
 * `variant="purchase"` is the one production purchase presentation: every locked paid
 * product renders identically — white surface, same border/radius/padding, price top-right.
 * `featured` is a compile error on that variant, so a purchase card can never drift into a
 * highlighted blue panel. Recommendation is expressed with a badge instead.
 */
type Props =
  | (BaseProps & { variant?: 'default'; featured?: boolean })
  | (BaseProps & { variant: 'purchase'; featured?: never });

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
  footer,
  disabled,
  retryable,
  onRetry,
  ...rest
}: Props) {
  const variant = (rest as { variant?: string }).variant ?? 'default';
  const featured = variant === 'purchase' ? false : (rest as { featured?: boolean }).featured;
  const showRetry = Boolean(disabled && retryable && onRetry);
  const showCta = Boolean(ctaLabel) || showRetry;
  const cta = !showCta ? null : showRetry ? (
    <button type="button" className="btn" style={{ width: '100%' }} onClick={onRetry}>
      가격 다시 확인하기
    </button>
  ) : to && !disabled ? (
    <Link className="btn" to={to} style={{ width: '100%' }}>
      {ctaLabel}
    </Link>
  ) : (
    <button
      type="button"
      className="btn"
      style={{ width: '100%' }}
      disabled={busy || disabled}
      onClick={disabled ? undefined : onClick}
    >
      {busy ? '준비 중…' : ctaLabel}
    </button>
  );

  return (
    <article
      className={`premium-card${variant === 'purchase' ? ' is-purchase' : ''}${
        featured ? ' is-featured' : ''
      }`}
    >
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
      {cta ? <div className="premium-cta">{cta}</div> : null}
      {footer ? <div className="premium-footer">{footer}</div> : null}
    </article>
  );
}
