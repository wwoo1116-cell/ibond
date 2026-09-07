# -*- coding: utf-8 -*-
"""응답 계약. [PROMPT_deploy_vercel «다음 레인» — 백엔드 먼저, 그다음 타입, 그다음 React]

## 왜 이 파일이 있는가

`snapshot()` 이 뱉는 dict 가 이 시스템의 유일한 계약인데 어디에도 안 적혀 있었고,
화면이 그걸 46곳에서 손으로 읽었다. 그 계약이 깨진 전례가 이미 있다 — 크레딧 엔트리에
`"s"` 키를 안 넣어 호가 1,824건이 통째로 책에서 빠졌는데, 타입도 시험도 아닌 런타임
검증기 [F4b] 가 잡았다.

여기에 적으면 세 가지가 따라온다.
  1. FastAPI 가 `/api/docs` 에 문서를 자동으로 낸다.
  2. OpenAPI → TypeScript 타입을 기계로 뽑을 수 있다(React 이식이 기계적 작업이 된다).
  3. 응답이 모델과 어긋나면 그 자리에서 안다.

## 무엇을 적고 무엇을 안 적는가

**행 8종과 계산된 뷰만 적는다.** 옛 스냅샷(`/book.json`)의 최상위 57키는 그대로 둔다 —
`hist`·`act`·`atbest` 처럼 «키가 종목코드인 자유로운 dict» 가 많아서 모델로 적으면
장황해지기만 하고 잡히는 것이 없다. 그건 화면이 `/api/view` 로 옮겨 가면 대부분 사라진다.

모든 필드에 `None` 을 허용한다. 이 책의 규칙이 «값이 없으면 없다고 보이게 한다» 이고,
그 규칙을 타입이 부정하면 안 된다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Side = Literal["S", "B"]
Lane = Literal["ktb", "msb", "nhb", "cr", "muni"]
AmountSource = Literal["stated", "implied", "bare", "default", "oddlot", "inherit"]
FillSource = Literal["stated", "level", "prev"]
LevelKind = Literal["quoted", "conv", "est"]


class Quote(BaseModel):
    """국고·통안·국민주택의 한 호가. (딜러, 방향, 종목) 하나에 하나뿐이다 — 절대값 교체."""
    t: int = Field(description="장중 초(00:00:00 부터)")
    s: Side | None = Field(None, description="S=매도(오퍼) · B=매수(비드)")
    y: float | None = Field(None, description="수익률(%). 없으면 레벨 미상이다")
    code: str | None = Field(None, description="국고 '25-10' · 통안 만기일 · 국주 사다리 칸")
    a: float | None = Field(None, description="수량(억). 표기가 없으면 기본단위 100")
    asrc: AmountSource | None = None
    d: str | None = Field(None, description="딜러 표시명. 가림이 켜져 있으면 'H01-2'")
    k: str | None = Field(None, description="딜러 키. 가림이 켜져 있으면 'K001'")
    atmp: bool | None = Field(None, description="레벨 없이 «민평에» 한다는 뜻의 호가")
    mp: float | None = Field(None, description="그 종목의 전일 민평(통안·국주만 싣는다)")
    mpd: str | None = Field(None, description="그 민평의 일자. 오늘이 아니면 «전일 대비»가 아니다")
    qr: float | None = Field(None, description="축약호가 원문(국주)")


class CreditQuote(BaseModel):
    """크레딧 매도 호가. ★이 시장은 반쪽이다 — 종목을 찍은 레벨 호가의 99.9%가 매도다."""
    t: int
    s: Side | None = None
    n: str | None = Field(None, description="종목/발행체 표시명")
    unit: Literal["bp", "원"] | None = Field(None, description="문면 표기 단위")
    atmp: bool | None = Field(None, description="문면에 값이 없어 «민평 그 자리» 로 읽은 오퍼 [OWNER 2026-09-07]")
    bp: float | None = Field(None, description="민평 대비 bp (bp 표기 행)")
    dbp: float | None = Field(None, description="민평 대비 bp (원 표기 행 — 끝전 환산 또는 문면 Δ)")
    bpe: float | None = Field(None, description="하류가 하나로 쓰는 민평 대비 bp")
    won: float | None = Field(None, description="문면 원 스프레드")
    ytm: float | None = None
    y: float | None = Field(None, description="ytm 과 같다(피드 호환)")
    mp: float | None = Field(None, description="문면에 적힌 전일 민평")
    ttm: float | None = Field(None, description="잔존(년)")
    matd: str | None = None
    cls: str | None = Field(None, description="종별(지방채·공사채·특은채·은행채·여전채·회사채)")
    cls2: str | None = Field(None, description="히트맵용 — 카드채를 여전채와 가른다")
    rt: str | None = Field(None, description="신용등급")
    rt_src: Literal["문면", "집계"] | None = None
    cats: list[str] | None = Field(None, description="범주 콜 매칭용 섹터")
    mb: int | None = Field(None, description="이 오퍼에 맞는 매수 니즈 수")
    frac: float | None = Field(None, description="끝전 — 전일 민평 단가의 소수부")
    fsrc: Literal["stated", "list", "assumed"] | None = None
    lvl: LevelKind | None = Field(None, description="quoted=문면 금리 · conv=끝전 환산 · est=0.5 가정")
    chk: float | None = Field(None, description="Q 행의 대사값(우리 환산 − 문면 금리, bp)")
    a: float | None = None
    asrc: AmountSource | None = None
    d: str | None = None
    k: str | None = None


class Fill(BaseModel):
    """체결 보고. ★«확인» 이 아니라 «보고» 다 — 같은 거래가 양쪽에서 두 번 올 수 있다."""
    t: int
    sec: str | None = None
    lane: Lane | None = None
    code: str | None = None
    n: str | None = None
    s: Side | None = None
    y: float | None = None
    a: float | None = None
    asrc: AmountSource | None = None
    csrc: FillSource | None = Field(None, description="종목을 어떻게 알았나. level 99.4% · prev 92.9%")
    ag: Side | None = Field(None, description="공격 방향. B=오퍼가 맞았다(누가 사 갔다) · S=비드가 맞았다(팔았다). 책에 붙지 않으면 없다")
    d: str | None = None
    k: str | None = None
    raw: str | None = Field(None, description="원문(가림이 켜져 있으면 서명은 라벨로 바뀐다)")
    room: str | None = None


class FeedRow(BaseModel):
    """메시지 한 줄. 파싱 결과를 원문과 나란히 흘린다."""
    i: int = Field(description="적재 일련번호. 화면이 이걸로 이어 붙인다")
    t: int
    r: str | None = Field(None, description="방")
    k: str | None = Field(None, description="종류 QUOTE·AXE·CONFIRM·INQUIRY·THANKS·OTHER")
    sec: str | None = None
    n: str | None = None
    code: str | None = None
    s: Side | None = None
    y: float | None = None
    bp: float | None = None
    a: float | None = None
    asrc: AmountSource | None = None
    atmp: bool | None = None
    csrc: FillSource | None = None
    lvl: LevelKind | None = None
    d: str | None = None
    bk: str | None = Field(None, description="딜러 키(가림 뒤 라벨)")
    h: str | None = Field(None, description="하우스(가림 뒤 라벨)")
    raw: str | None = None


class Dealer(BaseModel):
    """딜러(데스크)의 오늘. ★이름은 가림이 켜져 있으면 라벨이다."""
    k: str
    d: str | None = None
    n: int = Field(description="오늘 메시지 수")
    q: int = Field(description="그중 호가")
    b: int = Field(description="매수 호가")
    s: int = Field(description="매도 호가")
    c: int = Field(description="체결 응답")
    i: int = Field(description="관심·문의")
    first: int | None = None
    last: int | None = None
    lane: dict[str, int] | None = None
    codes: list[list] | None = Field(None, description="[[종목, 건수], …] 상위 6")
    ncode: int | None = None


class Event(BaseModel):
    """책의 «움직임». first=오늘 첫 호가 · best=최우선 갱신 · cross=남의 반대편을 뚫음
    · size=대량 · fill=체결. ★같은 레벨에서 만나는 «락» 은 이벤트가 아니다(하루 907건)."""
    t: int
    k: Literal["first", "best", "cross", "size", "fill"]
    lane: Lane | None = None
    code: str | None = None
    n: str | None = None
    s: Side | None = None
    y: float | None = None
    a: float | None = None
    d: str | None = None
    x: dict | None = Field(None, description="종류별 곁가지(이전 최우선·뚫은 상대·귀속 등급)")


class Swap(BaseModel):
    """교체(스위치). 축은 «신형 − 구형 bp» 이고 민평 대비가 아니다."""
    t: int
    s: Side | None = Field(None, description="신형을 사면 B, 팔면 S")
    y: float | None = Field(None, description="신형 − 구형(bp)")
    pair: str | None = Field(None, description="'구형/신형'")
    new: str | None = None
    old: str | None = None
    kind: str | None = Field(None, description="QUOTE=호가 · AXE=관심")
    a: float | None = None
    asrc: AmountSource | None = None
    d: str | None = None
    k: str | None = None


class Basket(BaseModel):
    """범주 콜 = 크레딧의 «매수면». 종목을 안 찍고 (잔존, 섹터, 등급)으로 온다."""
    t: int
    lo: float | None = None
    hi: float | None = None
    sec: str | None = None
    rt: str | None = None
    a: float | None = None
    asrc: AmountSource | None = None
    d: str | None = None
    ms: int | None = Field(None, description="이 니즈에 맞는 오퍼 수")
    bo: dict | None = Field(None, description="그중 가장 싼 것")


# ── 계산된 뷰 (/api/view) ────────────────────────────────────────────
class Axis(BaseModel):
    """레벨 없는 «관심». 종목·방향은 정해졌는데 값이 없는 호가 [OWNER 2026-09-07].

    09-01 판정으로 «호가» 라 부르지 않으므로 책에는 안 들어간다 — 이 목록에만 있다.
    """
    t: int
    lane: Lane | None = None
    code: str | None = None
    n: str | None = None
    s: Side | None = None
    a: float | None = None
    asrc: AmountSource | None = None
    d: str | None = None
    k: str | None = None


class BondRow(BaseModel):
    """종목 한 줄 — 서버가 활성 필터·무크로스·최우선·mid 를 계산해 준 것."""
    c: str
    nm: str | None = None
    full: str | None = None
    alias: str | None = None
    ten: str | None = None
    mat: str | None = None
    mp: float | None = None
    mpd: str | None = None
    fa: Quote | None = Field(None, description="최우선 오퍼")
    fb: Quote | None = Field(None, description="최우선 비드")
    mid: float | None = None
    fill: dict | None = Field(None, description="당일 마지막 체결 {t, y}")
    bench: bool = False
    next: bool = False
    today: bool = False
    n: int = 0
    nq: int = 0
    npx: int = 0
    hn: int = 0
    pv: dict | None = Field(None, description="어제 책의 그 종목")


class CreditBucket(BaseModel):
    """종별×등급 버킷. 값은 중앙값이다."""
    k: str
    cls: str
    rt: str
    est: bool = Field(False, description="등급이 문면이 아니라 집계에서 온 것")
    n: int
    nat: int = Field(0, description="그중 «민평에» 오퍼 수 — 중앙값에서는 뺀다 [OWNER 2026-09-07]")
    mb: int = 0
    bp_med: float | None = None
    ytm_med: float | None = None
    ttm_lo: float | None = None
    ttm_hi: float | None = None


class HeatCell(BaseModel):
    med: float | None = None
    n: int = 0
    lo: float | None = None
    hi: float | None = None
    est: int = Field(0, description="그 칸에 든 «추정»(끝전 0.5 가정) 건수")


class Heat(BaseModel):
    cells: dict[str, HeatCell]
    stale: bool = Field(False, description="통안 민평이 그날 것이 아니다")
    rows: list[list]
    buckets: list[str]


class CurveOffer(BaseModel):
    n: str | None = None
    ttm: float | None = None
    ytm: float | None = None
    bpe: float | None = None
    a: float | None = None
    mb: int = 0
    lvl: LevelKind | None = None


class Curve(BaseModel):
    offers: list[CurveOffer]
    mp_line: list[list] = Field(description="[[잔존, 민평 중앙값, 표본수], …]")
    mp_n: int = 0


class ObSide(BaseModel):
    """사다리 한 칸의 한 면. 화면은 이걸 막대로 그리기만 한다."""
    n: int
    amt: float
    unk: int = Field(0, description="수량 표기가 없던 호가 수")
    dflt: int = Field(0, description="표기가 없어 기본단위 100억으로 본 수")
    odd: int = Field(0, description="자투리")
    atmp: int = Field(0, description="«민평에» 라고만 한 호가 수")
    fresh: int = Field(0, description="그 칸에서 가장 신선한 호가의 장중 초")
    hit: int = Field(0, description="그 칸에서 «실제로 체결된» 호가 수 (v12 체결 귀속)")
    fhit: int = Field(0, description="그 칸의 마지막 체결 시각(장중 초). 0 이면 없음")
    who: list[str | None] = []


class ObLevel(BaseModel):
    y: float
    S: ObSide | None = None
    B: ObSide | None = None
    atmp: bool = False
    blank: Literal["a", "b"] | None = Field(None, description="집계 격자의 빈 칸")


class ObSum(BaseModel):
    a: float = 0
    b: float = 0
    na: int = 0
    nb: int = 0
    imp_a: float = 0
    imp_b: float = 0


class ObBest(BaseModel):
    fa: Quote | None = None
    fb: Quote | None = None
    spread_bp: float | None = None
    mid: float | None = None


class ObLadder(BaseModel):
    """종목 하나의 호가 사다리. 막대 폭·나이 칩은 값이 아니라 표현이라 여기 없다."""
    code: str
    agg: float = 0.0
    levels: list[ObLevel] = []
    implied: list[dict] = Field([], description="교체에서 나온 조건부 호가")
    basis: Literal["amt", "n"] = "n"
    mx: float = 1
    sum: ObSum = ObSum()
    best: ObBest = ObBest()


class DealerCard(BaseModel):
    """이 종목에 선 딜러 하나 — 가장 최근 오퍼/비드 한 건씩."""
    k: str | None = None
    d: str | None = None
    S: Quote | None = None
    B: Quote | None = None
    n: int = Field(0, description="오늘 이 종목에 낸 호가 건수")
    ab_s: float = Field(0, description="오늘 최우선 오퍼에 서 있던 시간(초)")
    ab_b: float = Field(0, description="오늘 최우선 비드에 서 있던 시간(초)")
    fresh: int = 0
    both: bool = False


class DealerCards(BaseModel):
    rows: list[DealerCard] = []
    n: int = 0
    n_both: int = 0
    fa_y: float | None = None
    fb_y: float | None = None


class SwapPair(BaseModel):
    pair: str | None = None
    asks: list[dict] = []
    bids: list[dict] = []
    spread_bp: float | None = Field(None, description="신형−구형 bp. ×100 하지 않는다")


class SwapBook(BaseModel):
    n: int = 0
    pairs: list[SwapPair] = []


class CurveTodayRow(BondRow):
    """커브 오늘의 한 줄 — 종목 행에 «전일민평 대비» 와 «딜러 수» 를 얹은 것."""
    dbp: float | None = Field(None, description="mid − 전일민평, bp")
    nd: str = Field("", description="오늘 오퍼 딜러 · 비드 딜러 수")


class PulseBin(BaseModel):
    t: int = Field(description="칸의 시작 장중 초")
    q: int = 0
    a: int = 0
    c: int = 0
    i: int = 0
    o: int = 0


class PulsePrevBin(BaseModel):
    t: int
    n: int = 0


class Pulse(BaseModel):
    """시장 맥박. 화면은 칸 값을 막대로 그리기만 한다."""
    bin: int = 600
    bins: list[PulseBin] = []
    prev_bins: list[PulsePrevBin] = []
    nq: int = 0
    na: int = 0
    nc: int = 0
    ni: int = 0
    ktb: int = 0
    cr: int = 0
    msb: int = 0
    vs_prev_pct: float | None = Field(None, description="어제 같은 시각까지 누적 대비 %")
    n_dealer: int = 0
    prev_n_dealer: int | None = None
    n_event: int = 0
    t0: int | None = None
    t1: int | None = None


class LeaderRow(BaseModel):
    k: str | None = None
    d: str | None = None
    n: int = 0
    ln: int = Field(0, description="고른 레인에서의 건수")
    s: int = 0
    b: int = 0
    c: int = 0
    ab: float = Field(0, description="오늘 최우선에 서 있던 시간 합(초)")
    first: int | None = None
    last: int | None = None
    lane: dict[str, int] = {}
    codes: list[list] = []


class Leaderboard(BaseModel):
    rows: list[LeaderRow] = []
    n: int = 0
    shown: int = 0


class PxPoint(BaseModel):
    t: int
    mid: float | None = None
    a: float | None = Field(None, description="그 시각의 최우선 오퍼")
    b: float | None = Field(None, description="그 시각의 최우선 비드")


class ActBin(BaseModel):
    t: int
    n: int = Field(0, description="막대 높이 — 화면과 같게 앞 둘의 합")
    tot: int = Field(0, description="척도용 합계")


class PxSeries(BaseModel):
    """시세 이력. 세로 범위는 규칙이라 서버가 낸다(민평 대칭)."""
    code: str
    mp: float | None = None
    lo: float | None = None
    hi: float | None = None
    t0: int | None = None
    t1: int | None = None
    bin: int = 600
    pts: list[PxPoint] = []
    act: list[ActBin] = []
    note: str | None = Field(None, description="표본이 모자라면 그 이유")


class GradePoint(BaseModel):
    ttm: float
    y: float


class GradeCurve(BaseModel):
    """등급별 민평 커브 한 벌(`sim_portfolio.credit_matrix` 최신 행)."""
    group: str | None = None
    date: str | None = None
    label: str | None = None
    pts: list[GradePoint] = []


class View(BaseModel):
    """`/api/view` 의 응답. 화면은 이걸 그대로 그린다."""
    now: str | None = None
    T: int
    ttl_mode: Literal["def", "half", "inf"] = "def"
    ver: int | None = None
    counts: dict[str, int]
    heat: Heat
    rows: list[BondRow] | None = Field(None, description="lane 이 ktb·msb·nhb 일 때")
    axes: list[Axis] | None = Field(None, description="레벨 없는 «관심» — 책이 아니다")
    buckets: list[CreditBucket] | None = Field(None, description="lane 이 cr 일 때")
    curve: Curve | None = None
    mtx_group: str | None = Field(None, description="credit_matrix 의 bond_type(등급 커브)")
    # 종목 하나를 고른 상태에서만 실린다. 화면이 다시 계산하지 않게 하려는 것이다.
    ob: ObLadder | None = Field(None, description="고른 종목의 호가 사다리")
    dealers: DealerCards | None = Field(None, description="누가 어디 서 있나")
    swap: SwapBook | None = Field(None, description="교체 책(국고만)")
    px: PxSeries | None = Field(None, description="고른 종목의 시세 이력")
    offers: list[CreditQuote] | None = Field(None, description="lane 이 cr 일 때 고른 버킷의 오퍼")
    needs: list[Basket] | None = Field(None, description="lane 이 cr 일 때 매수 니즈")
    grade_curve: GradeCurve | None = Field(None, description="고른 종별·등급의 민평 커브")
    # lane 이 dyn 일 때. 그림의 픽셀 좌표는 화면 몫이라 여기엔 칸 값만 있다.
    pulse: Pulse | None = None
    events: list[Event] | None = None
    event_counts: dict[str, int] | None = None
    curve_today: dict[str, list[CurveTodayRow]] | None = None
    leaderboard: Leaderboard | None = None
    aggr: dict[str, int] | None = Field(None, description="당일 공격 방향 집계 {B: 사 간 체결, S: 판 체결}")
