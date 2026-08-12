import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

function BrandMark() {
  return (
    <div className="brand-row" aria-label="VAgent">
      <span className="brand-mark" aria-hidden />
      <span className="brand-name">VAgent</span>
    </div>
  );
}

type Tab = 'record' | 'upload';

export default function Home() {
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>('record');

  return (
    <main>
      <BrandMark />

      <section className="home-hero">
        <p className="page-kicker">보컬 진단</p>
        <h1 className="brand">
          내 목소리는 지금
          <br />
          어떻게 쓰이고 있을까?
        </h1>
        <p className="lead home-hero-lead">
          노래 한 구절로 발성 타입과 두드러진 특징을 확인해보세요.
        </p>
        <p className="home-hero-meta">한 구절이면 충분해요 · 무료로 시작</p>
      </section>

      <div className="panel home-input-card">
        <h2 className="section-title" style={{ marginTop: 0 }}>분석할 음원을 준비해주세요</h2>

        <div className="segmented" role="tablist" aria-label="입력 방식">
          <button
            type="button"
            role="tab"
            className={tab === 'record' ? 'is-active' : ''}
            aria-selected={tab === 'record'}
            onClick={() => setTab('record')}
          >
            녹음하기
          </button>
          <button
            type="button"
            role="tab"
            className={tab === 'upload' ? 'is-active' : ''}
            aria-selected={tab === 'upload'}
            onClick={() => setTab('upload')}
          >
            파일 업로드
          </button>
        </div>

        {tab === 'record' ? (
          <>
            <h3 className="home-panel-title">직접 한 구절 불러주세요</h3>
            <p className="home-panel-desc">15~60초 정도가 가장 좋아요.</p>
            <ul className="record-idle-tips">
              <li>한 구절 정도가 좋아요</li>
              <li>조용한 환경을 권장해요</li>
              <li>반주가 있어도 분석할 수 있어요</li>
            </ul>
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/record')}>
              녹음 시작
            </button>
          </>
        ) : (
          <>
            <h3 className="home-panel-title">이미 녹음한 노래가 있나요?</h3>
            <p className="home-panel-desc">파일을 선택한 뒤 미리 들어보고 분석할 수 있어요.</p>
            <ul className="record-idle-tips">
              <li>m4a · mp3 · wav 등 지원</li>
              <li>15~60초 정도를 권장해요</li>
              <li>반주가 있어도 분석할 수 있어요</li>
            </ul>
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/upload')}>
              파일 선택
            </button>
          </>
        )}
      </div>

      <section className="section" style={{ borderBottom: 0, paddingBottom: 8 }}>
        <h2 className="section-title">어디까지 확인할까요?</h2>
        <div className="tier-grid">
          <div className="tier-card is-free">
            <p className="tier-label">FREE</p>
            <h3 className="tier-title">무료 보컬 리포트</h3>
            <p className="tier-body">발성 타입 · Head/Chest · 핵심 특징</p>
          </div>
          <div className="tier-card is-premium">
            <p className="tier-label">PREMIUM</p>
            <h3 className="tier-title">상세 리포트</h3>
            <p className="tier-body">5축 발성 프로필 · 추가 관찰 · 주요 구간</p>
          </div>
          <div className="tier-card is-premium">
            <p className="tier-label">PRECISION</p>
            <h3 className="tier-title">정밀 발성 진단</h3>
            <p className="tier-body">노래만으로 알기 어려운 항목을 추가 녹음으로 확인</p>
          </div>
        </div>
      </section>

      <div className="trust-note">
        <h3>노래만으로 부족한 부분은 한 번 더 확인해요</h3>
        <p>
          이미 충분히 분석된 항목은 다시 측정하지 않습니다.
          필요한 항목만 짧은 추가 녹음으로 확인해요.
        </p>
      </div>

      <div style={{ marginTop: 20 }}>
        <Link className="btn ghost" to="/history" style={{ width: '100%' }}>
          이전 결과 보기
        </Link>
      </div>

      <p className="footer-note">음향 기반 발성 분석 서비스 · 의료 진단이 아닙니다</p>
    </main>
  );
}
