"""
main.py — VAgent v2 CLI

Examples (PowerShell):
  python main.py sample.m4a --output runtime
  python main.py sample.m4a --feedback
  python main.py sample.m4a --separate
  python main.py sample.m4a --json
  python main.py sample.m4a --visualize --show
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from audio_analyzer import analyze_audio, public_result
from audio_analyzer.env_utils import load_dotenv_if_available


load_dotenv_if_available()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="노래 실력 진단받기 (VAgent v2) — 보컬 발성 분석 CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("audio_path", help="분석할 오디오 파일 경로")
    parser.add_argument("--output", "-o", default="runtime", help="결과 저장 루트")
    parser.add_argument("--id", dest="recording_id", default=None, help="녹음 ID")
    parser.add_argument("--sr", dest="sample_rate", type=int, default=44100)
    parser.add_argument("--user", dest="user_id", default=None)
    parser.add_argument("--title", dest="song_title", default=None)
    parser.add_argument("--artist", default=None)
    parser.add_argument("--section", default=None)
    parser.add_argument("--show", action="store_true", help="시각화 창 표시")
    parser.add_argument("--visualize", action="store_true", help="PNG 시각화 생성")
    parser.add_argument(
        "--separate",
        action="store_true",
        help="Demucs 보컬 분리 (기본 OFF — 이어폰 보이스 녹음 권장)",
    )
    parser.add_argument("--model", dest="demucs_model", default="htdemucs")
    parser.add_argument("--feedback", action="store_true", help="LLM/템플릿 피드백 생성")
    parser.add_argument("--api-key", dest="api_key", default=None)
    parser.add_argument(
        "--feedback-model",
        dest="feedback_model",
        default=os.environ.get("FEEDBACK_MODEL", "gpt-4o-mini"),
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=os.environ.get("BASE_URL"),
    )
    parser.add_argument(
        "--json",
        dest="json_stdout",
        action="store_true",
        help="public result JSON을 stdout에 출력",
    )
    parser.add_argument("--no-preview", action="store_true", help="preview.wav 생성 생략")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audio_path = Path(args.audio_path)
    if not audio_path.exists():
        print(f"[오류] 파일을 찾을 수 없음: {audio_path}", file=sys.stderr)
        sys.exit(1)

    feedback_kwargs = None
    if args.feedback:
        feedback_kwargs = {
            "api_key": args.api_key or os.environ.get("OPENAI_API_KEY"),
            "model": args.feedback_model,
            "base_url": args.base_url,
        }

    result = analyze_audio(
        audio_path=str(audio_path),
        output_dir=args.output,
        recording_id=args.recording_id,
        sample_rate=args.sample_rate,
        user_id=args.user_id,
        song_title=args.song_title,
        artist=args.artist,
        section=args.section,
        show=args.show,
        generate_visuals=args.visualize or args.show,
        separate=args.separate,
        demucs_model=args.demucs_model,
        build_preview=not args.no_preview,
        include_feedback=args.feedback,
        feedback_kwargs=feedback_kwargs,
    )

    pub = public_result(result)

    if args.json_stdout:
        payload = json.dumps(pub, ensure_ascii=False, indent=2)
        try:
            print(payload)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((payload + "\n").encode("utf-8", errors="replace"))
        return

    print("\n===== 분석 요약 (v2) =====")
    print(f"  recording_id : {result['recording_id']}")
    print(f"  duration     : {result['audio']['duration_sec']} s")
    print(f"  source_mode  : {result['audio']['source_mode']}")
    print(f"  quality      : {result['quality']['status']} (conf={result['quality']['confidence']})")
    score = result.get("score") or {}
    if score.get("available"):
        print(f"  overall      : {score.get('overall')} — {score.get('label')}")
        for area in score.get("areas") or []:
            print(
                f"    - {area['display_name']}: {area.get('score')} [{area.get('status')}]"
            )
    else:
        print(f"  score        : unavailable ({score.get('reason')})")
    print(f"  timeline     : {len(result.get('timeline') or [])} events")
    print(f"  feedback     : {result.get('feedback_status')}")
    out_dir = Path(args.output) / result["recording_id"]
    print(f"  saved        : {out_dir}")
    print("==========================\n")

    if args.feedback and result.get("feedback"):
        from audio_analyzer import build_user_friendly_report

        report = result["feedback"].get("user_friendly_report") or build_user_friendly_report(
            result["feedback"]
        )
        safe = report.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        )
        print(safe)


if __name__ == "__main__":
    main()
