import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { progressLinkState } from '../lib/progressNavigation';

type Tab = 'record' | 'upload';

const DEPTH_STEPS = [
  {
    title: '무료 리포트',
    badge: '무료',
    paid: false,
    body: '내 발성 타입과 주요 특징을 확인해보세요.',
  },
  {
    title: '상세 리포트',
    badge: '유료',
    paid: true,
    body: '특징이 나타난 실제 구간과 상세 발성 프로필을 확인해보세요.',
  },
  {
    title: '보컬 진단',
    badge: '유료',
    paid: true,
    body: '추가 녹음으로 다시 측정하고 목표 발성에 맞춘 피드백을 받아보세요.',
  },
] as const;

export default function Home() {
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>('record');

  return (
    <main>
      <section className="home-hero" data-testid="home-hero">
        <h1 className="home-hero-title">노래 실력 진단받기</h1>
        <p className="home-hero-subtitle">내 목소리는 지금 어떻게 쓰이고 있을까?</p>
        <p className="home-hero-desc">노래나 음성을 분석해 발성 타입과 특징을 보여드려요.</p>
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
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/record')}>
              녹음 시작
            </button>
            <p className="home-input-note">평소 부르듯 자연스럽게 불러보는 걸 추천해요.</p>
          </div>
        ) : (
          <div className="home-input-body">
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/upload')}>
              파일 선택
            </button>
            <p className="home-input-note">목소리가 잘 들리는 구간을 올리는 걸 추천해요.</p>
          </div>
        )}
      </section>

      <section className="home-depth" data-testid="home-depth" aria-label="분석이 깊어지는 순서">
        <ul className="home-depth-list">
          {DEPTH_STEPS.map((step) => (
            <li key={step.title} className="home-depth-item">
              <div className="home-depth-head">
                <h2 className="home-depth-title">{step.title}</h2>
                <span className={`home-depth-badge${step.paid ? ' is-paid' : ' is-free'}`}>{step.badge}</span>
              </div>
              <p className="home-depth-body">{step.body}</p>
            </li>
          ))}
        </ul>
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
      <nav className="home-service-info" aria-label="서비스 정보">
        <Link to="/service-info" data-testid="home-service-info-link">
          서비스 정보
        </Link>
      </nav>
    </main>
  );
}
