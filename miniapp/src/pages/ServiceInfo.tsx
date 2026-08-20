import { Link } from 'react-router-dom';

const BUSINESS = {
  name: '프랙토컬',
  representative: '강민혁',
  registration: '453-09-03373',
  address: '경상북도 구미시 대학로3길 45 우리행복 305호',
  phone: '010-9873-6677',
  email: 'uhaki04@gmail.com',
} as const;

export default function ServiceInfo() {
  return (
    <main data-testid="service-info">
      <h1 className="brand" style={{ fontSize: '1.45rem' }}>
        서비스 정보
      </h1>
      <p className="lead" style={{ marginTop: 4 }}>
        노래 실력 진단받기
      </p>

      <section className="service-info-block" aria-labelledby="service-info-business">
        <h2 id="service-info-business" className="service-info-heading">
          사업자 정보
        </h2>
        <dl className="service-info-dl">
          <div>
            <dt>상호</dt>
            <dd>{BUSINESS.name}</dd>
          </div>
          <div>
            <dt>대표자</dt>
            <dd>{BUSINESS.representative}</dd>
          </div>
          <div>
            <dt>사업자등록번호</dt>
            <dd>{BUSINESS.registration}</dd>
          </div>
          <div>
            <dt>사업장 주소</dt>
            <dd>{BUSINESS.address}</dd>
          </div>
          <div>
            <dt>전화</dt>
            <dd>{BUSINESS.phone}</dd>
          </div>
          <div>
            <dt>이메일</dt>
            <dd>{BUSINESS.email}</dd>
          </div>
        </dl>
      </section>

      <nav className="service-info-links" aria-label="법적 문서">
        <Link className="service-info-row" to="/legal/terms">
          <span>이용약관</span>
          <span aria-hidden="true">›</span>
        </Link>
        <Link className="service-info-row" to="/legal/privacy">
          <span>개인정보처리방침</span>
          <span aria-hidden="true">›</span>
        </Link>
      </nav>

      <section className="service-info-block" aria-labelledby="service-info-contact">
        <h2 id="service-info-contact" className="service-info-heading">
          문의
        </h2>
        <p className="service-info-contact">{BUSINESS.email}</p>
      </section>
    </main>
  );
}
