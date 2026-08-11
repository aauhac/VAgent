import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { loadUnlockedSessions } from '../api/client';

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
  const sessions = loadUnlockedSessions();
  const [tab, setTab] = useState<Tab>('record');

  return (
    <main>
      <BrandMark />

      <section style={{ marginTop: 20, marginBottom: 8 }}>
        <p className="page-kicker">보컬 진단</p>
        <h1 className="brand">
          내 목소리는 지금
          <br />
          어떻게 쓰이고 있을까?
        </h1>
        <p className="lead" style={{ marginBottom: 20 }}>
          노래 녹음 한 개로 발성 타입과 두드러진 특징을 분석합니다.
        </p>
        <div className="cta-row">
          <button type="button" className="btn" onClick={() => nav('/record')}>
            바로 녹음하기
          </button>
          <button type="button" className="btn secondary" onClick={() => nav('/upload')}>
            파일 업로드하기
          </button>
        </div>
      </section>

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

      <div className="panel" style={{ marginTop: 0 }}>
        {tab === 'record' ? (
          <>
            <h2 className="section-title" style={{ marginTop: 0 }}>짧게 불러보세요</h2>
            <ul className="record-idle-tips">
              <li>권장 길이 15~60초 · 한 구절 정도가 좋아요</li>
              <li>기본은 무반주(순수 보컬) 분석이에요</li>
              <li>반주가 있다면 녹음 화면에서 체크해 주세요</li>
            </ul>
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/record')}>
              녹음 시작하기
            </button>
          </>
        ) : (
          <>
            <h2 className="section-title" style={{ marginTop: 0 }}>파일을 올려보세요</h2>
            <ul className="record-idle-tips">
              <li>m4a / mp3 / wav 등 지원</li>
              <li>올린 뒤 미리듣기로 확인한 다음 분석해요</li>
              <li>반주가 있다면 업로드 화면에서 체크해 주세요</li>
            </ul>
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/upload')}>
              파일 선택하기
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
            <p className="tier-body">발성 타입 · 두드러진 특징 · 핵심 프로필을 바로 확인해요.</p>
          </div>
          <div className="tier-card is-premium">
            <p className="tier-label">PREMIUM</p>
            <h3 className="tier-title">상세 리포트</h3>
            <p className="tier-body">더 자세한 발성 프로필과 관찰 특징, 들어볼 구간을 확인해요.</p>
          </div>
          <div className="tier-card is-premium">
            <p className="tier-label">PRECISE</p>
            <h3 className="tier-title">정밀 발성 진단</h3>
            <p className="tier-body">추가 녹음으로 불확실한 항목만 더 정확하게 확인해요.</p>
          </div>
        </div>
      </section>

      <div className="trust-note">
        <h3>정밀 진단은 ‘더 비싼 결과’가 아니에요</h3>
        <p>
          노래 한 곡만으로는 확정하기 어려운 항목이 있을 때,
          필요한 짧은 과제만 추가 녹음해 정확도를 높이는 검사예요.
        </p>
      </div>

      <div style={{ marginTop: 20 }}>
        <Link className="btn ghost" to="/history" style={{ width: '100%' }}>
          이전 결과 보기
        </Link>
      </div>

      {sessions.length > 0 && (
        <section className="section">
          <h3 className="section-title" style={{ fontSize: '1.05rem' }}>정밀 진단 기록</h3>
          {sessions.slice(0, 5).map((sid) => (
            <Link
              key={sid}
              to={`/diagnostic/${sid}/report`}
              className="detail-row"
              style={{ textDecoration: 'none' }}
            >
              <span style={{ fontWeight: 600 }}>세션 {sid.slice(0, 8)}…</span>
              <span className="meta">보기 ›</span>
            </Link>
          ))}
        </section>
      )}

      <p className="footer-note">음향 기반 발성 분석 서비스 · 의료 진단이 아닙니다</p>
    </main>
  );
}
