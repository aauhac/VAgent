export const SMOKE_ANALYSIS_ID = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
export const SMOKE_SESSION_ID = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
export const SMOKE_TASK_ID = 'comfortable_glide';

export const detailReport = {
  vocal_type_profile: {
    available: true,
    display_name: '안정적인 발성형',
    headline: '안정적인 발성형',
    description: '이번 녹음에서는 힘이 과하지 않고 소리가 비교적 고르게 이어졌어요.',
    head_chest: { available: true, chest_ratio: 58, head_ratio: 42, show_ratio: true },
    canonical_register: {
      status: 'CONNECTED',
      title: '성구 연결이 자연스러워요',
      description: '고음으로 올라갈 때 소리가 크게 끊기지 않았어요.',
    },
    range_profiles: {
      low: { available: true, chest_ratio: 72, head_ratio: 28 },
      mid: { available: true, chest_ratio: 55, head_ratio: 45 },
      high: { available: true, chest_ratio: 38, head_ratio: 62 },
    },
  },
  vocal_style_profile: {
    available: true,
    display_name: '안정적인 발성형',
    description: '힘 조절이 무난하고 음색이 한쪽으로 치우치지 않았어요.',
    primary_traits: [
      { label: '힘', value: '낮음' },
      { label: '숨 섞임', value: '적음' },
      { label: '음색', value: '중간' },
    ],
    canonical_register: {
      status: 'CONNECTED',
      title: '성구 연결이 자연스러워요',
      description: '고음으로 올라갈 때 소리가 크게 끊기지 않았어요.',
    },
  },
  vocal_function_profile: {
    dimensions: [
      {
        dimension_id: 'vocal_effort_strain',
        status: 'LOW',
        confidence_label: 'medium',
        continuum_0_to_1: 0.28,
      },
      {
        dimension_id: 'air_leakage_breathiness',
        status: 'LOW',
        confidence_label: 'medium',
        continuum_0_to_1: 0.32,
      },
    ],
    coaching_decision: {
      primary_bottleneck: {
        title: '고음에서 힘이 살짝 들어가요',
        summary: '높은 음으로 갈수록 소리가 조금 더 세게 밀리는 느낌이 있어요.',
        original_start_sec: 8.2,
        original_end_sec: 11.4,
      },
      preserve: [{ title: '안정적인 기본 발성' }],
      target_episode: {
        core_evidence_span: { original_start_sec: 8.2, original_end_sec: 11.4 },
      },
    },
    high_note_function_profile: {
      available: true,
      summary: ['고음으로 올라갈 때 연결은 되지만 힘이 조금 붙어요.'],
      axes: {
        high_note_stability: { status: 'PRESERVED', summary: '고음에서도 비교적 안정적이에요.' },
        transition_continuity: { status: 'CONTINUOUS', summary: '고음 구간 연결이 자연스러운 편이에요.' },
        high_note_effort_cost: { status: 'INCREASED', summary: '고음에서 힘이 조금 붙어요.' },
      },
    },
    timbre_profile: {
      available: true,
      summary: ['음색이 한쪽으로 치우치지 않았어요.'],
      axes: {
        presence: { continuum: 0.55, display: '중간' },
        brightness: { continuum: 0.48, display: '중간' },
      },
    },
  },
  canonical_acoustic_axes: {
    axes: {
      brightness: { continuum: 0.48, display: '중간', available: true },
      breathiness: { continuum: 0.32, display: '적음', available: true },
      contact: { continuum: 0.52, display: '중간', available: true },
      presence: { continuum: 0.55, display: '중간', available: true },
    },
  },
  observation_segments: [{ label: '고음 구간', original_start_sec: 8.2, original_end_sec: 11.4 }],
  disclaimer: '음향 기반 발성 분석 서비스이며 의료 진단이 아닙니다.',
  diagnostic_offer: {
    unresolved_labels: ['고음 연결', '힘 조절'],
    recommended_task_count: 2,
  },
  access: {
    song_detail_unlocked: true,
    diagnostic_unlocked: false,
    diagnostic_session_id: null,
  },
};

export const productsCatalog = {
  environment: 'development',
  products: {
    song_detail: {
      product_id: 'song_detail',
      display_name: '상세 리포트',
      display_amount: '₩1,100',
      amount_source: 'toss_iap',
    },
    diagnostic_full: {
      product_id: 'diagnostic_full',
      display_name: '정밀 발성 진단',
      display_amount: '₩3,300',
      amount_source: 'toss_iap',
    },
    diagnostic_upgrade: {
      product_id: 'diagnostic_upgrade',
      display_name: '정밀 발성 진단 업그레이드',
      display_amount: '₩2,200',
      amount_source: 'toss_iap',
    },
  },
  offers: {
    song_detail: null,
    diagnostic: 'diagnostic_upgrade',
  },
};

export const analysisAccess = {
  analysis_id: SMOKE_ANALYSIS_ID,
  song_detail_unlocked: true,
  diagnostic_unlocked: false,
  diagnostic_session_id: null,
};

export const progressInsight = {
  status: 'ok',
  insight_available: true,
  history_count: 4,
  goal_aware: false,
  today: [{ axis: 'effort', title: '힘 사용', label: '낮음' }],
  improved: [
    {
      axis: 'effort',
      title: '힘 사용',
      current_raw: 'LOW',
      current_label: '낮음',
      baseline_modal_raw: 'HIGH',
      baseline_modal_label: '높음',
      kind: 'IMPROVED',
      headline: '힘이 덜 들어가고 있어요',
      detail: '최근 녹음에서 힘을 덜 쓰는 쪽으로 바뀌었어요.',
    },
  ],
  changed: [
    {
      axis: 'brightness',
      title: '음색 밝기',
      current_raw: 'MID',
      current_label: '중간',
      baseline_modal_raw: 'DARK',
      baseline_modal_label: '어두운 편',
      kind: 'CHANGED',
      headline: '음색이 조금 달라졌어요',
      detail: '이전보다 조금 더 밝은 쪽으로 들렸어요.',
    },
  ],
  maintained: [
    {
      axis: 'breathiness',
      title: '숨 섞임',
      current_raw: 'LOW',
      current_label: '적음',
      baseline_modal_raw: 'LOW',
      baseline_modal_label: '적음',
      kind: 'MAINTAINED',
      headline: '숨 섞임은 비슷해요',
      detail: '최근 기록에서도 숨이 많이 섞이지 않았어요.',
    },
  ],
  source: 'server',
};

export const precisionReport = {
  report_title: '정밀 발성 진단',
  report_subtitle: '추가 녹음으로 고음 연결과 힘 조절을 더 확인해 정리했어요.',
  source_analysis_id: SMOKE_ANALYSIS_ID,
  evidence_mode: 'FULL_PRECISION',
  vocal_type_profile: {
    available: true,
    display_name: '안정적인 발성형',
    description: '기본 발성은 안정적이고, 고음에서만 힘이 조금 붙어요.',
  },
  vocal_style_profile: {
    available: true,
    display_name: '안정적인 발성형',
    description: '힘과 숨 섞임이 한쪽으로 치우치지 않았어요.',
    primary_traits: [
      { label: '힘', value: '낮음' },
      { label: '고음', value: '연결되나 힘이 붙음' },
    ],
  },
  reliable_findings: [
    {
      mechanism_id: 'phonatory_effort',
      title: '고음에서 힘이 붙어요',
      summary: '높은 음으로 갈수록 소리가 조금 더 세게 밀렸어요.',
    },
  ],
  uncertain_findings: [
    {
      mechanism_id: 'register_transition',
      summary: '성구 전환은 이번 과제만으로 단정하기 어려워요.',
    },
  ],
  supporting_observations: [{ summary: '낮은 음에서는 소리가 비교적 고르게 유지됐어요.' }],
  completed_tasks: [SMOKE_TASK_ID],
  canonical_register: {
    status: 'CONNECTED',
    title: '성구 연결이 자연스러워요',
    description: '고음으로 올라갈 때 크게 끊기지는 않았어요.',
  },
  canonical_acoustic_axes: {
    axes: {
      brightness: { continuum: 0.5, display: '중간', available: true },
      breathiness: { continuum: 0.3, display: '적음', available: true },
    },
  },
  coaching_goal: {
    desired_outcome: { type: 'EFFORT', label: '고음에서 힘을 덜 쓰기' },
    practices: [{ title: '편한 미끄럼 발성', body: '힘을 빼고 낮은 음에서 높은 음으로 이어보세요.' }],
    preserve_labels: ['안정적인 기본 발성'],
  },
  coaching_protocol: {
    steps: [
      { title: '편안한 미끄럼', instruction: '낮은 음에서 높은 음까지 한 번에 이어보세요.' },
      { title: '짧은 고음 유지', instruction: '편한 고음을 2초만 유지해 보세요.' },
    ],
  },
  safety: {
    disclaimer: '음향 기반 발성 분석 서비스이며 의료 진단이 아닙니다.',
  },
  personalized_qa: {
    coaching: {
      task_profiles: {
        [SMOKE_TASK_ID]: {
          task: '편안한 미끄럼 발성',
          rows: [{ label: '힘', value: '고음에서 조금 증가' }],
        },
      },
    },
  },
};

export const diagnosticSession = {
  session_id: SMOKE_SESSION_ID,
  status: 'PAID',
  diagnostic_status: 'NORMAL',
  source_analysis_id: SMOKE_ANALYSIS_ID,
  next_task_id: SMOKE_TASK_ID,
  selected_tasks: [SMOKE_TASK_ID, 'easy_onset'],
  diagnostic_offer: { unresolved_labels: ['고음 연결', '힘 조절'] },
  task_plan: [
    {
      task_id: SMOKE_TASK_ID,
      title: '편안한 미끄럼 발성',
      why: '고음으로 올라갈 때 힘이 어떻게 붙는지 확인해요.',
      instruction: '낮은 음에서 높은 음까지 한 번에 미끄러지듯 이어보세요. 크게 지르지 않아도 됩니다.',
      purpose_labels: ['고음 연결', '힘 조절'],
    },
    {
      task_id: 'easy_onset',
      title: '편한 소리 시작',
      why: '소리가 어떻게 시작되는지 확인해요.',
      instruction: '편하게 “아”로 시작해 보세요.',
      purpose_labels: ['시작 조절'],
    },
  ],
};

export const diagnosticProtocol = {
  tasks: diagnosticSession.task_plan,
};

export const historyPayload = {
  items: [
    {
      analysis_id: SMOKE_ANALYSIS_ID,
      created_at: '2026-08-17T12:00:00Z',
      filename: '연습곡_고음이_조금_힘들었던_녹음.wav',
      vocal_type: '안정적인 발성형',
      status: 'completed',
      song_detail_unlocked: true,
      diagnostic_unlocked: true,
      diagnostic_session_id: SMOKE_SESSION_ID,
      diagnostic_sessions: [
        {
          session_id: SMOKE_SESSION_ID,
          status: 'COMPLETED',
          created_at: '2026-08-17T12:30:00Z',
          completed_at: '2026-08-17T12:40:00Z',
        },
      ],
    },
  ],
  unlinked_diagnostics: [],
  has_more: false,
};
