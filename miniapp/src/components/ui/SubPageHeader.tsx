import { Link } from 'react-router-dom';

type Props = {
  title: string;
  onBack: () => void;
  homeTo?: string;
  backLabel?: string;
  homeLabel?: string;
};

/**
 * Sub-page header: ‹ 뒤로 | title | 홈
 * Grid keeps title visually centered regardless of action widths.
 */
export default function SubPageHeader({
  title,
  onBack,
  homeTo = '/',
  backLabel = '뒤로',
  homeLabel = '홈',
}: Props) {
  return (
    <header className="sub-page-header" data-testid="sub-page-header">
      <button
        type="button"
        className="sub-page-header__action sub-page-header__back"
        onClick={onBack}
        aria-label="이전 화면으로 돌아가기"
      >
        ‹ {backLabel}
      </button>
      <h1 className="sub-page-header__title">{title}</h1>
      <Link
        className="sub-page-header__action sub-page-header__home"
        to={homeTo}
        aria-label="홈으로 이동"
      >
        {homeLabel}
      </Link>
    </header>
  );
}
