import type { DisplayAxis } from '../../lib/reportPresentation';
import { buildVocalAxes } from '../../lib/reportPresentation';
import SpectrumAxis from './SpectrumAxis';

type Props = {
  dimensions: any;
  criteriaMatrix?: any[];
  title?: string;
  axes?: DisplayAxis[];
  showConfidence?: boolean;
  canonicalRegister?: { status?: string; profile_label?: string; title?: string } | null;
  canonicalAcoustic?: { axes?: Record<string, any> } | null;
};

export default function VocalProfile({
  dimensions,
  criteriaMatrix = [],
  title = '내 발성 프로필',
  axes: axesProp,
  showConfidence = true,
  canonicalRegister,
  canonicalAcoustic,
}: Props) {
  const axes = axesProp || buildVocalAxes(dimensions, criteriaMatrix, canonicalRegister, canonicalAcoustic);

  return (
    <section className="section">
      <h3 className="section-title">{title}</h3>
      {axes.length === 0 ? (
        <p className="body-text muted">
          이번 녹음에서는 발성 프로필을 안정적으로 구성하지 못했어요.
        </p>
      ) : (
        axes.map((ax) => (
          <SpectrumAxis
            key={ax.id}
            label={ax.label}
            leftLabel={ax.left}
            rightLabel={ax.right}
            value={ax.value ?? 0}
            stateLabel={ax.display}
            confidencePercent={ax.confidence_percent}
            confidenceLabel={ax.confidence_label}
            showConfidence={showConfidence}
          />
        ))
      )}
    </section>
  );
}
