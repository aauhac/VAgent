import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { progressLinkState } from '../lib/progressNavigation';

type Tab = 'record' | 'upload';

export default function Home() {
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>('record');

  return (
    <main>
      <section className="home-hero" data-testid="home-hero">
        <p className="page-kicker">노래 실력 진단받기</p>
        <h1 className="brand">
          내 목소리는 지금
          <br />
          어떻게 쓰이고 있을까?
        </h1>
        <p className="lead home-hero-lead">
          노래 한 구절로
          <br />
          발성 타입과 두드러진 특징을 확인해보세요.
        </p>
      </section>

      <section className="home-input" data-testid="home-input">
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
          <div className="home-input-body">
            <p className="home-panel-desc">15~60초 한 구절이면 충분해요.</p>
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/record')}>
              녹음 시작
            </button>
          </div>
        ) : (
          <div className="home-input-body">
            <p className="home-panel-desc">이미 있는 파일을 올려 분석할 수 있어요.</p>
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/upload')}>
              파일 선택
            </button>
          </div>
        )}
      </section>

      <section className="home-compare" data-testid="home-product-compare">
        <h2 className="section-title">분석 단계</h2>
        <div className="compare-rows">
          <div className="compare-row">
            <h3 className="compare-title">무료 보컬 리포트</h3>
            <p className="compare-body">발성 타입 · 핵심 특징 · 현재 발성 상태</p>
          </div>
          <div className="compare-row">
            <h3 className="compare-title">상세 리포트</h3>
            <p className="compare-body">고음·음색 심층 분석 · 주요 구간 듣기 · 연습 목표 설정</p>
          </div>
          <div className="compare-row">
            <h3 className="compare-title">정밀 발성 진단</h3>
            <p className="compare-body">추가 녹음 · 정밀 확인 · 우선 연습 부분 · 단계별 피드백</p>
          </div>
        </div>
      </section>

      <div className="home-links">
        <Link
          className="btn secondary"
          to="/progress"
          state={progressLinkState('/')}
          style={{ width: '100%' }}
          data-testid="home-progress-link"
        >
          내 변화 보기
        </Link>
        <Link className="btn ghost" to="/history" style={{ width: '100%' }}>
          분석 기록
        </Link>
      </div>
      <nav className="home-legal" aria-label="약관">
        <Link to="/legal/terms">이용약관</Link>
        <Link to="/legal/privacy">개인정보처리방침</Link>
      </nav>
    </main>
  );
}
