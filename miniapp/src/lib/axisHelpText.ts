/**
 * Central help copy for vocal / timbre profile axes.
 * Keep user-facing explanations here — do not duplicate strings in components.
 */

export const AXIS_HELP_TEXT: Record<string, string> = {
  CONTACT:
    '소리가 가볍게 접촉하는지 단단하게 접촉하는지 보는 경향이에요. 단단할수록 소리 중심이 또렷하게 느껴질 수 있지만, 이 값 하나만으로 가성·진성을 판정하지는 않아요.',
  BREATHINESS:
    '소리에 숨결이나 잡음 성분이 얼마나 섞이는지 보여줘요. 왼쪽일수록 숨 섞임이 적고, 오른쪽일수록 숨결이 더 느껴지는 편이에요.',
  EFFORT:
    '음향에서 소리를 밀어붙이는 것과 일치할 수 있는 특징이 얼마나 나타나는지 봐요. 실제 목 근육의 힘을 직접 측정하는 값은 아니에요.',
  REGISTER_CONNECTION:
    '음역이 올라갈 때 발성 특성이 얼마나 자연스럽게 이어지는지 봐요. 왼쪽일수록 변화가 갑작스럽고, 오른쪽일수록 연결이 매끄러운 편이에요.',
  PRESENCE:
    '중역대에서 소리의 중심과 존재감이 얼마나 유지되는지 보여줘요. 높을수록 소리가 또렷하고 존재감 있게 느껴질 수 있어요.',
  BRIGHTNESS:
    '전체 주파수 분포를 바탕으로 음색이 어둡거나 밝게 느껴지는 경향을 보여줘요. 음량과는 다른 특징이에요.',
  TIMBRE_AIRINESS:
    '음색에서 숨결이 느껴지는 정도예요. 숨 섞임과 관련은 있지만, 음색을 설명하기 위한 별도 표현이에요.',
  TEXTURE:
    '음색이 매끈하게 들리는지 거칠게 느껴지는지 보여줘요. 거친 쪽이라고 해서 좋고 나쁘거나 병적이라는 뜻은 아니에요.',
  HARMONIC_CONCENTRATION:
    '배음 에너지가 얼마나 분산되거나 집중되어 나타나는지 보는 경향이에요. 높고 낮음에 좋고 나쁨은 없어요.',
  TIMBRE_CONSISTENCY:
    '비슷한 음높이와 강도에서 음색이 얼마나 일정하게 유지되는지 보여줘요.',
  STABILITY:
    '지속되는 소리에서 음높이와 진동 특성이 얼마나 안정적으로 유지되는지 보는 경향이에요.',
};

/** Map display axis ids used in UI → help dictionary keys */
export const AXIS_ID_TO_HELP_KEY: Record<string, keyof typeof AXIS_HELP_TEXT> = {
  contact: 'CONTACT',
  breath: 'BREATHINESS',
  breathiness: 'BREATHINESS',
  effort: 'EFFORT',
  register: 'REGISTER_CONNECTION',
  resonance: 'PRESENCE',
  presence: 'PRESENCE',
  brightness: 'BRIGHTNESS',
  airiness: 'TIMBRE_AIRINESS',
  texture: 'TEXTURE',
  harmonic_concentration: 'HARMONIC_CONCENTRATION',
  timbre_consistency: 'TIMBRE_CONSISTENCY',
  stability: 'STABILITY',
};

export function helpTextForAxis(axisId: string): string | undefined {
  const key = AXIS_ID_TO_HELP_KEY[axisId];
  return key ? AXIS_HELP_TEXT[key] : undefined;
}
