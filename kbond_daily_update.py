# -*- coding: utf-8 -*-
"""K-Bond 증분 갱신.

자동저장 로그는 장중 내내 append 된다(실측: 08-28 블커본드 08:45:34~16:50:55).
그래서 실시간 수집기 없이 이 파일들만 다시 읽으면 그날치가 다 들어온다.
[OWNER 2026-09-01] 수집기 폐기, 증분 파싱이 주 경로.

동작
  1) (방,날짜) 그룹별 지문(파일명·크기·mtime)을 상태파일과 대조해 더러운 그룹만 고른다.
     파일이 자라기만 해도 지문이 바뀌므로 16:30 실행이 놓친 꼬리는 다음 실행에서 회수된다.
  2) 더러운 그룹만 parse_kbond_logs.parse_group 으로 다시 판다.
     중복 제거가 그룹 안에서 닫히므로 그룹 재파싱은 멱등하다.
  3) 기존 parquet 을 행그룹 단위로 흘려보내며 더러운 (Room,Date) 행을 빼고,
     새로 판 행을 뒤에 붙여 임시파일에 쓴 뒤 원자적으로 교체한다.
     830만 행을 한 DataFrame 으로 들지 않는다(T8).
  4) enrich_kbond_quotes.main() 을 부른다. 그쪽은 파생열을 지우고 다시 만들므로 멱등하다.

사용
  python kbond_daily_update.py              # 증분
  python kbond_daily_update.py --force      # 전 그룹 재파싱(부트스트랩)
  python kbond_daily_update.py --no-enrich  # 파싱만
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from parse_kbond_logs import (COLUMNS, EXTS, PA_SCHEMA, ROOMS, SRC_DIR, file_meta,
                              parse_group)

BASE = Path(r"C:\Users\infomax\Projects\data\kbond")
PARQUET = BASE / "kbond_structured_data.parquet"
STATE = BASE / "kbond_parse_state.json"
LOG = BASE / "kbond_daily_update.log"


def say(msg: str) -> None:
    line = f"{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# --------------------------------------------------------------- 1. 그룹/지문
def scan_groups() -> dict[str, list[str]]:
    """(방,날짜) -> 파일 목록. 키는 상태파일에 담기게 'room|YYYYMMDD' 문자열."""
    if not SRC_DIR.is_dir():
        sys.exit(f"[FATAL] 경로 없음: {SRC_DIR}")
    groups: dict[str, list[str]] = defaultdict(list)
    for p in SRC_DIR.iterdir():
        if p.suffix.lower() not in EXTS:
            continue
        if not any(r in p.name for r in ROOMS):
            continue
        room, date = file_meta(p)
        room = next((r for r in ROOMS if r in room), room)
        if date is None:
            continue
        groups[f"{room}|{date}"].append(str(p))
    return {k: sorted(v) for k, v in groups.items()}


def fingerprint(paths: list[str]) -> list[list]:
    """파일명·크기·mtime. 파일이 자라면 바뀐다."""
    out = []
    for s in paths:
        st = os.stat(s)
        out.append([Path(s).name, st.st_size, int(st.st_mtime)])
    return sorted(out)


# --------------------------------------------------------------- 2. 파싱
FLUSH_ROWS = 300_000          # 이 이상 모이면 흘려보낸다. 830만을 한 번에 들지 않는다(T8).


def typed(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    df["Timestamp"] = pd.to_datetime(df["Date"] + " " + df["Time"],
                                     format="%Y%m%d %H:%M:%S", errors="coerce")
    df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d", errors="coerce")
    for c in ("OddLot", "AmountImplied", "IsInquiry"):
        df[c] = df[c].astype("boolean")
    return df


def iter_parsed(dirty: list[str], groups: dict[str, list[str]], workers: int):
    """더러운 그룹을 병렬로 파싱해 FLUSH_ROWS 단위 DataFrame 으로 흘려보낸다."""
    tasks = [(k.split("|", 1)[0], k.split("|", 1)[1], groups[k]) for k in dirty]
    buf, errors, n_done = [], [], 0
    if workers > 1 and len(tasks) > 1:
        pool = ProcessPoolExecutor(max_workers=workers)
        stream = pool.map(parse_group, tasks, chunksize=4)
    else:
        pool, stream = None, map(parse_group, tasks)
    try:
        for _room, _date, _nraw, _nnoise, got in stream:
            n_done += 1
            errors += [r["_error"] for r in got if "_error" in r]
            buf += [r for r in got if "_error" not in r]
            if len(buf) >= FLUSH_ROWS:
                yield typed(buf)
                buf = []
            if n_done % 200 == 0:
                say(f"      파싱 {n_done:,}/{len(tasks):,} 그룹")
    finally:
        if pool is not None:
            pool.shutdown()
    if buf:
        yield typed(buf)
    for e in errors[:5]:
        say(f"      읽기 실패 {e}")


# --------------------------------------------------------------- 3. 스플라이스
def rewrite(dirty: list[str], groups: dict[str, list[str]], workers: int):
    """더러운 (Room,Date) 행을 빼고 새로 판 행을 붙인 parquet 을 새로 쓴다."""
    drop_keys = {(k.split("|")[0], pd.Timestamp(k.split("|")[1])) for k in dirty}
    tmp = PARQUET.with_suffix(".parquet.tmp")
    if tmp.exists():
        tmp.unlink()
    if not PARQUET.exists():
        sys.exit("[FATAL] 기준 parquet 이 없다. parse_kbond_logs.py 로 한 번 전량 생성할 것")

    src = pq.ParquetFile(PARQUET)
    base = src.schema_arrow
    # ★2026-09-02: 여기서 `schema = src.schema_arrow` 를 그대로 쓰고 아래에서
    # `df = df[names]` 로 잘라 내는 바람에 **파서가 새로 만든 열이 조용히
    # 사라졌다**(범주 콜 4열이 그렇게 없어졌고, 47열로 나온 뒤에야 알았다).
    # 파스 쪽 스키마의 유일한 출처는 `parse_kbond_logs.PA_SCHEMA` 다. 거기에
    # 있는데 기존 파일에 없는 열은 이어붙이고, 옛 행에는 결측으로 채운다.
    _extra = [f for f in PA_SCHEMA if f.name not in base.names]
    if _extra:
        say(f"      [스키마] 새 열 {len(_extra)}개 추가: "
            f"{[f.name for f in _extra]}")
    schema = pa.schema(list(base) + _extra)
    names = [f.name for f in schema]
    writer = pq.ParquetWriter(tmp, schema, compression="zstd")
    kept = added = 0
    full = len(dirty) >= len(groups)      # 전 그룹 재파싱이면 복사 단계는 순수 낭비
    try:
        for i in range(0 if full else src.num_row_groups):
            chunk = src.read_row_group(i).to_pandas()
            keep = ~pd.MultiIndex.from_arrays(
                [chunk["Room"], chunk["Date"]]).isin(drop_keys)
            chunk = chunk[keep]
            for _f in _extra:                   # 옛 행에는 새 열이 없다
                if _f.name not in chunk.columns:
                    chunk[_f.name] = pd.Series([pd.NA] * len(chunk), dtype="object")
            if len(chunk):
                chunk = chunk[names]
                kept += len(chunk)
                writer.write_table(
                    pa.Table.from_pandas(chunk, preserve_index=False).cast(schema))
            del chunk
        say(f"      기존 유지 {kept:,}행")

        for df in iter_parsed(dirty, groups, workers):
            for n in names:                     # 파생열(enrich 몫)은 결측으로 둔다
                if n not in df.columns:
                    df[n] = pd.Series([pd.NA] * len(df), dtype="object")
            df = df[names]
            added += len(df)
            writer.write_table(
                pa.Table.from_pandas(df, preserve_index=False).cast(schema))
            say(f"      신규 누적 {added:,}행")
            del df
    finally:
        writer.close()
        src.close()          # 안 닫으면 Windows 가 os.replace 를 거부한다(WinError 5)

    if added == 0 and kept == 0:
        tmp.unlink(missing_ok=True)
        sys.exit("[FATAL] 결과가 0행이다. 원본을 건드리지 않고 중단한다")
    os.replace(tmp, PARQUET)
    return kept, added


# --------------------------------------------------------------- 3b. 결측 감시
def warn_missing(groups: dict[str, list[str]], back: int = 10) -> None:
    """최근 평일에 자동저장 파일이 아예 없는 날을 알린다.

    앱이 안 떠 있으면 파일이 안 생기고, 그런 날은 어떤 수집 경로로도 못 막는다
    (실측: 2026-08-31 월요일). 조용히 비는 대신 로그에 남긴다.
    """
    have = {k.split("|", 1)[1] for k in groups}
    today = pd.Timestamp.now().normalize()
    days = pd.bdate_range(end=today, periods=back).strftime("%Y%m%d")
    miss = [d for d in days if d not in have and d != today.strftime("%Y%m%d")]
    if miss:
        say(f"  [경고] 최근 {back}영업일 중 로그 없는 날 {len(miss)}개: {miss}")
    else:
        say(f"  최근 {back}영업일 로그 결측 없음")


# --------------------------------------------------------------- 4. main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="전 그룹 재파싱")
    ap.add_argument("--no-enrich", action="store_true")
    ap.add_argument("--state-only", action="store_true",
                    help="parquet 은 건드리지 않고 지문 상태만 다시 쓴다")
    ap.add_argument("--workers", type=int, default=min(10, os.cpu_count() or 4))
    args = ap.parse_args()

    t0 = time.time()
    say("=" * 66)
    say("K-Bond 증분 갱신 시작")

    groups = scan_groups()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    fps = {k: fingerprint(v) for k, v in groups.items()}

    if args.force or not state:
        dirty = sorted(groups)
        say(f"  부트스트랩(상태파일 없음 또는 --force): 전 그룹 {len(dirty):,}개")
    else:
        dirty = sorted(k for k, fp in fps.items() if state.get(k) != fp)
        gone = sorted(set(state) - set(groups))
        if gone:
            say(f"  사라진 그룹 {len(gone)}개(무시): {gone[:3]}")
    say(f"  그룹 {len(groups):,}개 중 갱신 대상 {len(dirty):,}개")
    for k in dirty[:10]:
        say(f"      {k}")
    if len(dirty) > 10:
        say(f"      ... 외 {len(dirty) - 10}개")

    warn_missing(groups)

    if args.state_only:
        STATE.write_text(json.dumps(fps, ensure_ascii=False), encoding="utf-8")
        say(f"  지문 상태만 재작성 ({len(fps):,} 그룹). parquet 은 안 건드렸다.")
        return 0

    if not dirty:
        say(f"  변경 없음. 종료 ({time.time() - t0:.0f}초)")
        return 0

    kept, added = rewrite(dirty, groups, args.workers)
    say(f"  유지 {kept:,} + 신규 {added:,} = {kept + added:,}행")

    STATE.write_text(json.dumps(fps, ensure_ascii=False), encoding="utf-8")

    if not args.no_enrich:
        say("  enrich 실행")
        import enrich_kbond_quotes
        enrich_kbond_quotes.main()
        say("  다리 재생성 (kbond_legs)")
        import kbond_legs
        kbond_legs.main()
        say("  체결 기록 재생성 (kbond_fills)")
        import kbond_fills
        kbond_fills.main()
        say("  KIS 예상종가 커브 (kbond_kis)")
        import kbond_kis
        kbond_kis.main()

    say(f"  완료 {time.time() - t0:,.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
