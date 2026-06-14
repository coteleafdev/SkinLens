#!/usr/bin/env python3
"""scripts/sync_breakpoint_domains.py — 브레이크포인트 이중 소스 정리.

문제
----
config.json 에 같은 metric 의 breakpoints 가 두 곳에 있고 도메인이 어긋난다.
  · /breakpoints                          ← 코드(_breakpoints._get_metric_bp)가 실제 읽는 SSOT
  · /prescription/measurements/*/breakpoints  ← 어떤 코드도 읽지 않는 죽은 사본(드리프트)

예) eye/nasolabial: top=magnitude(max 115) vs prescription=ratio(max 0.6/0.78)
    fine_deep:       top=ratio(max 0.7)     vs prescription=magnitude(max 500)

이 스크립트는 prescription 측 breakpoints 를 top-level 값으로 동기화한다(비파괴·멱등).
삭제를 원하면 --delete 로 prescription 측 breakpoints 키 자체를 제거한다.
어느 쪽이든 실행 후 L10(test_overall_and_crosstalk) 이 통과해야 한다.

사용:
  python scripts/sync_breakpoint_domains.py            # dry-run(변경 미리보기)
  python scripts/sync_breakpoint_domains.py --apply    # 동기화 적용
  python scripts/sync_breakpoint_domains.py --apply --delete  # prescription bp 제거
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_METRICS = (
    "eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score",
    "acne_score",
)


def _domain(bp) -> str:
    mx = max(float(p[0]) for p in bp)
    return f"{'ratio' if mx <= 1.0 else 'magnitude'}(max {mx:g})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--apply", action="store_true", help="실제로 파일에 기록")
    ap.add_argument("--delete", action="store_true",
                    help="동기화 대신 prescription 측 breakpoints 키 삭제")
    args = ap.parse_args()

    path = Path(args.config)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    top = cfg.get("breakpoints", {}) or {}
    pres = ((cfg.get("prescription", {}) or {}).get("measurements", {}) or {})

    changed = []
    for m in _METRICS:
        tbp = top.get(m)
        node = pres.get(m)
        if not isinstance(node, dict) or "breakpoints" not in node:
            continue
        pbp = node["breakpoints"]
        if not isinstance(pbp, list) or not tbp:
            continue
        if args.delete:
            changed.append((m, _domain(pbp), "삭제"))
            if args.apply:
                node.pop("breakpoints", None)
        else:
            if _domain(pbp) != _domain(tbp) or pbp != tbp:
                changed.append((m, _domain(pbp), _domain(tbp)))
                if args.apply:
                    node["breakpoints"] = json.loads(json.dumps(tbp))  # deep copy

    if not changed:
        print("변경 없음 — 이미 일관됨.")
        return 0

    print(f"{'적용' if args.apply else 'DRY-RUN'} 대상 {len(changed)}건:")
    for m, before, after in changed:
        print(f"  {m:28} {before:22} -> {after}")

    if args.apply:
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"기록 완료: {path}")
    else:
        print("\n미적용(dry-run). 적용하려면 --apply 추가.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
