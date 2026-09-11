# -*- coding: utf-8 -*-
"""K-Bond 백엔드 (FastAPI). [OWNER 2026-09-03 「계산과 집계는 서버, 화면은 그 값을 쓴다」]

## 무엇이 달라지는가

옛 `kbond_live.py` 는 파이썬 표준 `http.server` 한 파일에 책 엔진과 HTTP 껍데기가
같이 있었고, 원시 호가 목록을 통째로 보내면 화면이 받을 때마다 활성 필터·무크로스·
최우선·중앙값·히트맵 칸을 다시 계산했다. 그래서 같은 규칙이 파이썬과 자바스크립트
두 벌로 존재했다.

여기서는 계산이 한 곳(`kbond_view.py`)에 있고 화면은 받은 것을 그린다.

## 무엇이 그대로인가

**책 엔진은 한 글자도 안 건드린다.** `kbond_live.start_engine()` 을 그대로 부른다 —
파싱·복원·가림·체결 귀속·이벤트는 전부 그 안에 있고, `verify_v4.py` 가 검증하는
대상도 그것이다. 이 파일은 껍데기다.

## 끝점

    GET /health                     문턱 밖. 살아 있는지.
    GET /book.json                  옛 스냅샷 그대로 (화면 전환 전까지 호환)
    GET /feed.json?since=&limit=    메시지 피드 (h=/d=/k= 로 하우스·데스크·딜러 필터)
    GET /events                     SSE — 책이 바뀔 때 스냅샷을 민다
    GET /api/view?lane=&ttl=&cls=   ★계산된 값. 화면이 그대로 그린다.
    GET /                           화면 HTML

실행:  python -m uvicorn kbond_api:app --host 127.0.0.1 --port 8302
       (옛 판은 `python kbond_live.py`. 둘은 같은 엔진을 쓰고 포트만 다르다.)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
import kbond_live as KL                                          # noqa: E402
import kbond_view as KV                                          # noqa: E402
from kbond_schema import (Basket, CreditQuote, Dealer, Event, FeedRow,   # noqa: E402
                          Fill, Quote, Swap, View)

VIEWER = Path(__file__).parent / "kbond_live.html"
# ★[OWNER 2026-09-11] 새 화면(kbond-web)을 «같은 주소» 에 함께 낸다.
#   /       옛 화면(그대로)        ·  /app   새 화면
#   Funnel 에서는 /kbond/ 와 /kbond/app 이 된다.
#   ⚠두 자리에 붙이는 이유: Tailscale 이 `/kbond` 를 떼고 넘기는데 브라우저는 떼기
#     전 주소(/kbond/app/_next/...)로 자산을 부른다. 그래서 /app 과 /kbond/app 둘 다
#     같은 폴더를 봐야 한다. 로컬(127.0.0.1:8301/app/)도 그 덕에 그대로 돈다.
#   빌드는 `kbond-webuild_app.ps1` 가 굽는다(out-kbond). 없으면 조용히 안 붙인다 —
#   화면 하나가 없다고 책이 멈출 이유는 없다.
APP_DIR = Path(__file__).resolve().parent.parent / "kbond-web" / "out-kbond"
POLL_S = KL.POLL_S


@asynccontextmanager
async def lifespan(app: FastAPI):
    """책을 세우고 폴링을 시작한다. 옛 판의 main() 과 같은 절차를 같은 함수로 부른다."""
    at = None
    if os.getenv("KBOND_REPLAY"):
        KL.REPLAY = os.environ["KBOND_REPLAY"]
        if os.getenv("KBOND_AT"):
            h, m, s = (os.environ["KBOND_AT"] + ":0:0").split(":")[:3]
            at = KL.REPLAY_AT = int(h) * 3600 + int(m) * 60 + int(s)
    if os.getenv("KBOND_NO_MASK"):
        KL.MASK = False
    book, poll, ref = KL.start_engine(at=at)
    app.state.book = book

    stop = threading.Event()

    def loop():
        while not stop.is_set():
            time.sleep(POLL_S)
            try:
                poll()
            except Exception as e:                               # noqa: BLE001
                KL.log(f"[poll 오류] {type(e).__name__}: {e}")
                time.sleep(2)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    KL.log("[FastAPI] 기동 — 계산은 서버에서(kbond_view), 화면은 그린다")
    yield
    stop.set()


app = FastAPI(title="K-Bond", lifespan=lifespan, docs_url="/api/docs")

# ★CORS 는 미들웨어 두 줄이 된다(옛 판은 응답마다 손으로 붙였다).
#   규율은 그대로다 — `*` 금지, 앞뒤 앵커, 오리진 에코.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(KL.DEV_ORIGINS),
    allow_origin_regex=KL.DEFAULT_ORIGIN_REGEX,
    allow_methods=["GET"],
    allow_headers=["*"],
)
# 스냅샷이 809KB 다 — 밖으로 나가면 압축이 필수다(93KB). SSE 는 스트림이라 제외된다.
app.add_middleware(GZipMiddleware, minimum_size=4096)


def _deny_if_no_token(t):
    """토큰이 설정돼 있을 때만 검사한다. 지금은 [OWNER] 결정으로 꺼져 있다."""
    if not KL.token_ok(t):
        return Response(status_code=401)
    return None


def _snapshot():
    with KL.STATE["lock"]:
        return KL.STATE["book"], KL.STATE["raw"], KL.STATE["ver"]


@app.get("/health")
def health(t: str | None = None):
    if not KL.token_ok(t):
        return {"ok": True}
    with KL.STATE["lock"]:
        ver, last = KL.STATE["ver"], KL.STATE["last_evt"]
    return {"ok": True, "uptime_s": round(time.time() - KL.STATE["t0"]), "ver": ver,
            "last_event_age_s": round(time.time() - last, 1) if last else None,
            "masked": KL.MASK, "engine": "fastapi"}


@app.get("/book.json")
def book_json(t: str | None = None):
    """옛 스냅샷 그대로. 화면이 /api/view 로 옮겨 갈 때까지 남긴다."""
    d = _deny_if_no_token(t)
    if d:
        return d
    _, raw, _ = _snapshot()
    return Response(raw, media_type="application/json; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


class FeedPage(BaseModel):
    feed: list[FeedRow]
    n_seq: int


@app.get("/feed.json", response_model=FeedPage)
def feed_json(t: str | None = None, since: int = 0, limit: int = 4000,
              h: str | None = None, d: str | None = None, k: str | None = None):
    deny = _deny_if_no_token(t)
    if deny:
        return deny
    with KL.STATE["lock"]:
        st = list(KL.STATE["stream"])
    for want, fld in ((h, "h"), (d, "d"), (k, "bk")):
        if want:
            st = [e for e in st if e.get(fld) == want]
    limit = max(1, min(limit, 24000))
    rows = [e for e in st if e["i"] > since][-limit:]
    return JSONResponse({"feed": rows, "n_seq": st[-1]["i"] if st else 0},
                        headers={"Cache-Control": "no-store"})


@app.get("/api/view", response_model=View)
def api_view(t: str | None = None, lane: str = "ktb", ttl: str = "def",
             cls: str | None = None, rt: str | None = None,
             code: str | None = None, agg: float = 0.0,
             T: int | None = Query(None)):
    """★화면이 그릴 값. 활성 필터·무크로스·최우선·중앙값·히트맵을 여기서 계산한다.

    lane: ktb | msb | nhb | cr · ttl: def | half | inf
    cls·rt: 크레딧에서 고른 종별·등급(등급 커브 선택에 쓴다)
    """
    deny = _deny_if_no_token(t)
    if deny:
        return deny
    snap, _, ver = _snapshot()
    if not snap:
        return JSONResponse({"error": "책이 아직 안 섰습니다"}, status_code=503)
    out = KV.view(snap, lane=lane, T=T, mode=ttl, cls=cls, rt=rt,
                  code=code, agg=agg)
    out["ver"] = ver
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


@app.get("/events")
async def events(request: Request, t: str | None = None):
    """SSE. 책이 바뀔 때만 민다. 15초 조용하면 하트비트(끊김 오인 방지)."""
    if not KL.token_ok(t):
        return Response(status_code=401)

    async def gen():
        sent = -1
        while True:
            if await request.is_disconnected():
                return
            with KL.STATE["lock"]:
                ver, raw = KL.STATE["ver"], KL.STATE["raw"]
            if ver != sent:
                sent = ver
                yield b"data: " + raw + b"\n\n"
            else:
                hb = json.dumps({"now": time.strftime("%H:%M:%S"), "ver": ver}).encode()
                yield b"event: hb\ndata: " + hb + b"\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


@app.get("/", response_class=HTMLResponse)
def index():
    """화면은 문턱 밖이다 — 비밀은 데이터이지 화면이 아니다."""
    return HTMLResponse(VIEWER.read_text(encoding="utf-8"))


# ★마운트는 라우트 «뒤» 에 와야 한다 — StaticFiles 를 먼저 붙이면 경로를 삼킨다.
if APP_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles                  # noqa: E402

    app.mount("/kbond/app", StaticFiles(directory=APP_DIR, html=True), name="app-funnel")
    app.mount("/app", StaticFiles(directory=APP_DIR, html=True), name="app")
    KL.log(f"[화면] 새 화면을 /app 에 붙였다 — {APP_DIR}")
else:
    KL.log(f"[화면] 새 화면 빌드가 없다(건너뜀) — {APP_DIR}")
