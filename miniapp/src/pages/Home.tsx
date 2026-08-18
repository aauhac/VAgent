import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { progressLinkState } from '../lib/progressNavigation';

type Tab = 'record' | 'upload';

const DEPTH_STEPS = [
  {
    title: '무료 리포트',
    badge: '무료',
    paid: false,
    body: '내 발성 타입과 가장 두드러진 특징을 확인하고, 지금 내 목소리가 어떻게 쓰이고 있는지 먼저 알아보세요.',
  },
  {
    title: '상세 리포트',
    badge: '유료',
    paid: true,
    body: '무료 리포트에서 발견한 특징이 실제 노래의 어느 구간에서 나타나는지 확인해보세요. 고음·음색 변화와 상세 발성 프로필까지 더 깊게 살펴볼 수 있어요.',
  },
  {
    title: '보컬 진단',
    badge: '유료',
    paid: true,
    body: '노래만으로는 확인하기 어려웠던 발성 특성을 추가 녹음으로 다시 측정해보세요. 내가 신경 쓰였던 부분까지 반영해 한층 더 개인화된 발성 피드백을 확인할 수 있어요.',
  },
] as const;

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
          노래나 음성을 분석해서
          <br />
          발성 타입과 두드러진 특징을 보여드려요.
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
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/record')}>
              녹음 시작
            </button>
          </div>
        ) : (
          <div className="home-input-body">
            <button type="button" className="btn" style={{ width: '100%' }} onClick={() => nav('/upload')}>
              파일 선택
            </button>
          </div>
        )}
      </section>
      <p className="home-input-note">15~60초 한 구절이면 충분해요.</p>

      <section className="home-depth" data-testid="home-depth" aria-label="분석이 깊어지는 순서">
        <ol className="home-depth-list">
          {DEPTH_STEPS.map((step, index) => (
            <li key={step.title} className="home-depth-item">
              <div className="home-depth-head">
                <span className="home-depth-index" aria-hidden="true">
                  {index + 1}
                </span>
                <h2 className="home-depth-title">{step.title}</h2>
                <span className={`home-depth-badge${step.paid ? ' is-paid' : ' is-free'}`}>{step.badge}</span>
              </div>
              <p className="home-depth-body">{step.body}</p>
            </li>
          ))}
        </ol>
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
