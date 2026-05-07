"""
main.py
-------
커맨드라인 진입점.

사용 예)
    python main.py sample.mp3 --output outputs --id rec_test --title "My Song"
"""

import argparse
import json
import os
import sys
from pathlib import Path

from audio_analyzer import analyze_mp3
from audio_analyzer.env_utils import load_dotenv_if_available


load_dotenv_if_available()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="보컬 음색 분석기 -- MP3 -> analysis.json + 시각화 이미지",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("audio_path", help="분석할 오디오 파일 경로 (mp3, wav, m4a …)")
    parser.add_argument(
        "--output", "-o", default="outputs", help="결과 저장 루트 폴더"
    )
    parser.add_argument("--id", dest="recording_id", default=None, help="녹음 ID")
    parser.add_argument("--sr", dest="sample_rate", type=int, default=44100, help="샘플레이트")
    parser.add_argument("--segment", dest="segment_sec", type=float, default=5.0, help="구간 분할 초")
    parser.add_argument("--user", dest="user_id", default=None, help="사용자 ID")
    parser.add_argument("--title", dest="song_title", default=None, help="곡 제목")
    parser.add_argument("--artist", default=None, help="아티스트명")
    parser.add_argument("--section", default=None, help="구간 이름 (verse / chorus 등)")
    parser.add_argument(
        "--show",
        action="store_true",
        help="분석 후 파형/스펙트로그램/Pitch 곡선을 대화형 창으로 표시한다",
    )
    parser.add_argument(
        "--no-echo-reduction",
        action="store_true",
        help="에코/잔향 완화 전처리를 끈다 (기본은 켜짐)",
    )
    parser.add_argument(
        "--separate",
        action="store_true",
        help="Demucs로 보컬을 분리한 뒤 분석한다 (MR 포함 음원에 권장)",
    )
    parser.add_argument(
        "--model",
        dest="demucs_model",
        default="htdemucs",
        help="Demucs 모델명 (기본값: htdemucs)",
    )

    # LLM 피드백 옵션
    parser.add_argument(
        "--feedback",
        action="store_true",
        help="분석 후 LLM으로 보컬 피드백(feedback.json)을 생성한다",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="OpenAI 또는 vLLM API 키. 미입력 시 OPENAI_API_KEY 환경변수 사용",
    )
    parser.add_argument(
        "--feedback-model",
        dest="feedback_model",
        default=os.environ.get("FEEDBACK_MODEL", "gpt-4o-mini"),
        help="피드백 생성 모델명 (기본값: gpt-4o-mini). vLLM이면 Qwen/Qwen2.5-7B-Instruct 등",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=os.environ.get("BASE_URL"),
        help="vLLM 등 로컬 서버 URL (예: http://localhost:8000/v1). 미입력 시 OpenAI 공식 endpoint 사용",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    audio_path = Path(args.audio_path)
    if not audio_path.exists():
        print(f"[오류] 파일을 찾을 수 없음: {audio_path}", file=sys.stderr)
        sys.exit(1)

    supported = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}
    if audio_path.suffix.lower() not in supported:
        print(f"[경고] '{audio_path.suffix}' 포맷은 지원되지 않을 수 있습니다. 지원 포맷: {', '.join(supported)}")

    result = analyze_mp3(
        audio_path=str(audio_path),
        output_dir=args.output,
        recording_id=args.recording_id,
        sample_rate=args.sample_rate,
        segment_sec=args.segment_sec,
        user_id=args.user_id,
        song_title=args.song_title,
        artist=args.artist,
        section=args.section,
        show=args.show,
        separate=args.separate,
        demucs_model=args.demucs_model,
        reduce_echo=not args.no_echo_reduction,
    )

    # 간단한 요약 출력
    print("\n===== 분석 요약 =====")
    print(f"  recording_id : {result['recording_id']}")
    print(f"  duration     : {result['audio_meta']['duration_sec']} s")
    print(f"  f0_mean      : {result['pitch_features'].get('f0_mean_hz')} Hz")
    print(f"  pitch_stability : {result['pitch_features'].get('pitch_stability_cents')} cents")
    print(f"  detected_issues: {result['detected_issues']}")

    out_dir = Path(args.output) / result["recording_id"]
    print(f"\n  결과 저장 위치: {out_dir}")
    print("=====================\n")

    # LLM 피드백 생성
    if args.feedback:
        from audio_analyzer import generate_feedback_from_files, build_user_friendly_report

        api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print(
                "[오류] API 키가 없습니다. --api-key 옵션 또는 OPENAI_API_KEY 환경변수를 설정하세요.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"[feedback] 피드백 생성 중 (모델: {args.feedback_model}) ...")
        feedback = generate_feedback_from_files(
            output_dir=args.output,
            recording_id=result["recording_id"],
            api_key=api_key,
            model=args.feedback_model,
            base_url=args.base_url,
        )
        fb_path = out_dir / "feedback.json"
        report_path = out_dir / "feedback_report.txt"
        print(f"[feedback] 완료 → {fb_path}")
        print(f"  confidence    : {feedback.get('confidence')}")
        print(f"  overall       : {feedback.get('overall_summary', '')[:80]}")
        print(f"  needs_work    : {len(feedback.get('needs_work', []))}개 항목")
        print(f"  practice plan : {len(feedback.get('practice_plan', []))}개 항목")
        print(f"  report text   : {report_path}")

        detailed_report = feedback.get("user_friendly_report") or build_user_friendly_report(feedback)
        print("\n===== 사용자용 상세 피드백 =====")
        # Windows cp949 콘솔에서 표현 불가 문자 → 가장 유사한 ASCII로 대체
        safe_report = detailed_report.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
        print(safe_report)
        print("===============================\n")


if __name__ == "__main__":
    main()

