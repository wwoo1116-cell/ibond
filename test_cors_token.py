# -*- coding: utf-8 -*-
"""CORS·토큰 문턱 단위시험. [PROMPT_deploy_vercel_2026-09-03.md [1] 검증]

    python -m pytest test_cors_token.py -q

이 API 는 Funnel 로 «인터넷» 에 공개된다. 문턱은 토큰과 CORS 둘뿐이라, 둘 중 하나가
조용히 헐거워지면 아무도 모른다. 그래서 규칙을 여기에 고정한다.

Book 은 만들지 않는다 — 문턱은 `Handler` 의 일이고, 책을 세우려면 DB·로그가 필요해서
시험이 환경에 묶인다. `STATE` 만 채우고 핸들러를 띄운다(민평 로드 20초를 안 기다린다).
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import kbond_live as KL                                          # noqa: E402

PORT = 8399          # 시험 전용. :8301(프로덕션)·:8305(리플레이) 와 겹치지 않는다.
TOKEN = "test-token-abc"

DENY = [
    "https://ibond-theta.vercel.app.evil.com",  # 뒤에 붙인 도메인
    "https://evil-ibond-theta.vercel.app",      # 앞에 붙인 라벨
    "http://ibond-theta.vercel.app",            # 평문
    # ★접미사 없는 `ibond.vercel.app` 은 우리 것이 아니다(남이 쓰고 있다).
    #   우리 프로덕션은 `ibond-theta.vercel.app` 이다.
    "https://ibond.vercel.app",
]
ALLOW = [
    "https://ibond-theta.vercel.app",                              # 프로덕션
    "https://ibond-657gyrkkg-wwoo1116-6173s-projects.vercel.app",  # 프리뷰
    "http://127.0.0.1:8305",
]


# ── 순수 함수 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("origin", ALLOW)
def test_origin_allowed(origin):
    assert KL.origin_allowed(origin)


@pytest.mark.parametrize("origin", DENY + ["", "null", "https://vercel.app"])
def test_origin_denied(origin):
    assert not KL.origin_allowed(origin)


def test_regex_has_anchors():
    """앵커가 빠지면 `...vercel.app.evil.com` 이 통과한다. 눈으로도 못 보는 실수라 못 박는다."""
    assert KL.DEFAULT_ORIGIN_REGEX.startswith(r"\A")
    assert KL.DEFAULT_ORIGIN_REGEX.endswith(r"\Z")


def test_token_off_means_no_check(monkeypatch):
    monkeypatch.setattr(KL, "TOKEN", "")
    assert KL.token_ok(None) and KL.token_ok("아무거나")


def test_token_on(monkeypatch):
    monkeypatch.setattr(KL, "TOKEN", TOKEN)
    assert KL.token_ok(TOKEN)
    assert not KL.token_ok(None)
    assert not KL.token_ok("")
    assert not KL.token_ok(TOKEN + "x")
    assert not KL.token_ok(TOKEN[:-1])


# ── 실제 HTTP ────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def server():
    KL.TOKEN = TOKEN
    KL.STATE["raw"] = json.dumps({"ok": 1}).encode()
    KL.STATE["stream"] = []
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), KL.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{PORT}"
    srv.shutdown()
    KL.TOKEN = ""


def get(url, origin=None):
    req = urllib.request.Request(url)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


@pytest.mark.parametrize("path", ["/book.json", "/feed.json"])
def test_no_token_is_401(server, path):
    st, _, body = get(f"{server}{path}")
    assert st == 401 and body == b""


@pytest.mark.parametrize("path", ["/book.json", "/feed.json"])
def test_wrong_token_is_401(server, path):
    assert get(f"{server}{path}?t=nope")[0] == 401


@pytest.mark.parametrize("path", ["/book.json", "/feed.json"])
def test_right_token_is_200(server, path):
    assert get(f"{server}{path}?t={TOKEN}")[0] == 200


def test_html_open_without_token(server, tmp_path, monkeypatch):
    """화면(HTML)은 문턱 밖이다 — 막으면 로컬에서 화면 자체가 안 뜬다.
    비밀은 데이터이지 화면이 아니고, 같은 파일이 Vercel 에서도 공개로 배달된다."""
    f = tmp_path / "v.html"
    f.write_text("<html>hi</html>", encoding="utf-8")
    monkeypatch.setattr(KL, "VIEWER", f)
    st, _, body = get(f"{server}/")
    assert st == 200 and b"hi" in body


def test_health_open_without_token(server):
    """Funnel 이 살아 있는지 밖에서 보려면 필요하다 — 대신 «살아 있다» 만 준다."""
    st, _, body = get(f"{server}/health")
    d = json.loads(body)
    assert st == 200 and d == {"ok": True}


def test_health_detailed_with_token(server):
    d = json.loads(get(f"{server}/health?t={TOKEN}")[1] and get(f"{server}/health?t={TOKEN}")[2])
    assert d["ok"] and "uptime_s" in d and "ver" in d


@pytest.mark.parametrize("origin", ALLOW)
def test_cors_echo(server, origin):
    _, h, _ = get(f"{server}/book.json?t={TOKEN}", origin=origin)
    assert h.get("Access-Control-Allow-Origin") == origin
    assert "Origin" in (h.get("Vary") or "")


@pytest.mark.parametrize("origin", DENY)
def test_cors_denied(server, origin):
    """거절은 «헤더를 안 붙이는» 것으로 한다 — 브라우저가 막는다."""
    _, h, _ = get(f"{server}/book.json?t={TOKEN}", origin=origin)
    assert "Access-Control-Allow-Origin" not in h


def test_no_origin_header_is_fine(server):
    """curl 처럼 Origin 없이 오는 것은 CORS 대상이 아니다."""
    st, h, _ = get(f"{server}/book.json?t={TOKEN}")
    assert st == 200 and "Access-Control-Allow-Origin" not in h


def test_token_never_logged(server, tmp_path, monkeypatch):
    """토큰 값이 우리 로그에 남으면 안 된다."""
    seen = []
    monkeypatch.setattr(KL, "log", lambda m: seen.append(str(m)))
    get(f"{server}/book.json?t=wrong-{TOKEN}", origin="https://evil.example")
    assert not any(TOKEN in m for m in seen)
