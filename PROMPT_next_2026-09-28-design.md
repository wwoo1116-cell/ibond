# K-Bond 디자인 문법 — 정본 한 장 [2026-09-28]

> 09-28 낮의 「경량화」 인계문(`PROMPT_next_2026-09-28.md`)을 **대체하지 않는다.** 저쪽이 레인의
> 상태·배관·함정이고, 이 장은 **화면 문법**이다. 둘을 같이 읽는다.

## §0. 붙여 넣을 블록

```
K-Bond 화면 문법. [OWNER 2026-09-28] 「디자인 문법들 전반적으로 다듬기 — v2 문법 참조」로
하루 만에 옮겼다. 규칙은 전부 sauron-v2 에서 왔고, 이 앱만의 예외는 이유와 함께 코드에 적혀 있다.

정본 —  Projects\apps\kbond\PROMPT_next_2026-09-28-design.md   (이 파일 · 문법)
        Projects\apps\kbond\PROMPT_next_2026-09-28.md          (레인 상태·배관·함정)
        Projects\apps\sauron-v2\DESIGN.md · CLAUDE.md          (규칙의 출처)

★규칙을 기억할 필요 없다 — `kbond-web/guards/` 126개가 잰다. `pnpm test`.
★화면을 고쳤으면 셋: 지문 ×2(0건) · probe(0건) · 눈으로 한 장. §3.

문법 한 줄씩 —
- 차트 생김새는 `chart/useLwChart.ts:canonOptions` 한 곳. 격자 없음 · y축 오른쪽 ·
  조용한 눈금 · 자석 십자선 · 리드아웃은 **그림 밖 한 줄**(범례를 흡수한다).
- 숫자는 `lib/format.ts` 한 파일. 컴포넌트 안에서 toFixed·padStart·toLocaleString 금지.
- 변화는 **네 부품 한 벌** `ui/Delta` — 틴트 + 방향 클래스 + 화살표 ↗↘ + 부호 없는 숫자.
- 방향색은 **부호**(`.sr-up/.sr-down`)와 **매매**(`.kb-side-b/.kb-side-s`)에만.
  범주는 `--sr-ref-*`, 레벨은 잉크, 틴트 위 글자도 잉크.
- 표 폭은 `lib/columns.ts` 의 **서식 최대치** → `<ColGroup>`. 인라인 px 금지.
- 말줄임은 «이름 칸» 에만, 그것도 `title` 이 전체를 줄 때만. 조용한 잘림이 금지다.
- 반지름은 CDS 스케일, 글자는 11·12·13·14 + CDS 단(16·20·28), 「선택됨」은 `--sr-control`
  하나, 포커스 링은 잉크 2px 하나.
- 무거운 차트는 `next/dynamic` 으로만. `lightweight-charts` 는 `src/chart` 안에서만.
```

## §1. 무엇이 바뀌었나 — 한 문단

차트 넷이 눈금 알고리즘을 셋 갖고 있었고, 숫자 서식이 파일마다 여섯 벌이었고(그중 하나는
`+1.5bpbp` 를 냈다), 방향색이 부호 말고 다섯 가지 다른 뜻을 지고 있었고, 표 다섯이 폭을 안
주고 있었다. v2 의 규칙은 이미 이 리포에 **바이트 단위로 복사돼** 있었는데(토큰 파일 넷)
**참조가 0** 이었다 — 규칙이 있었는데 아무도 안 부르고 있었다. 그것을 부르게 했다.

## §2. 규칙과 그 «예외»

예외는 일곱이고 전부 코드에 이유가 적혀 있다.

| 자리 | 캐논 | 이 앱 | 왜 |
|---|---|---|---|
| 시세 여백 | 위 .08 / 아래 .04 | **대칭** | 「전일 민평이 정중앙」이 오너 규칙(09-03) |
| 시세 주선 | 순변화 방향색 | **잉크** | 빨강·파랑이 이미 매수·매도다 |
| 시세 면 | `area: 'dots'` | **없음** | 면 높이가 «대칭 구간 바닥에서의 거리» 라 없는 양을 그린다 |
| 커브 | lightweight-charts | **SVG** | LWC 에 산점도가 없다. v2 자신의 산점도도 SVG(`rv/RvScatter.tsx`) |
| 범주색 | `--sr-obj-*` | **`--sr-ref-*`** | obj 는 다크 전용(흰 카드 위 1.5~2.7:1). ref 넷은 라이트·다크 쌍이 ≈5:1 실측 |
| 말줄임 | 절대 금지 | **이름 칸 여덟** | 이름은 서식이 아니라 자료다. 폭을 실측 최대치로 넓히고 · «…» 로 보이게 자르고 · `title` 이 전체를 준다 |
| 리드아웃 유휴 | 마지막 표본을 읽는다(v2 §8.5b) | **오늘 폭·지금 자리** | 마지막 표본 넷이 전부 카드 머리·축에 이미 있는 수다 — [OWNER] 「너무 눈에 안 들어와」의 원인이 «작아서» 가 아니라 «아무것도 새로 말하지 않아서» 였다. 빈 상태는 여전히 없다(높이 고정) |

## §3. 화면을 고쳤으면 — 셋

```
cd C:\Users\infomax\Projects\apps\kbond
set KBOND_REPLAY=20260903&& set KBOND_AT=15:30:00&& python -X utf8 -m uvicorn kbond_api:app --host 127.0.0.1 --port 8302
cd ..\kbond-web && powershell -NoProfile -File build_app.ps1 && python -m http.server 3400 --directory out
chrome --headless=new --remote-debugging-port=9222 --user-data-dir=%TEMP%\kbchrome about:blank

cd ..\kbond
node compare_screens.mjs http://127.0.0.1:8302/ http://127.0.0.1:3400/ http://127.0.0.1:8302   # ×2 · 전부 0
node probe_screen.mjs   http://127.0.0.1:3400/ http://127.0.0.1:8302 메인 동향 국고 크레딧      # 0건
node shot_screen.mjs    http://127.0.0.1:3400/ http://127.0.0.1:8302 ob.png 국고 26-7           # 눈으로
node measure_load.mjs   http://127.0.0.1:3400/ http://127.0.0.1:8302 국고                        # 무게
cd ..\kbond-web && pnpm test                                                                     # guards 126
```

**도구 셋이 각자 다른 것을 본다.** `compare_screens` 는 두 화면이 «같은 수» 를 말하는지,
`probe_screen` 은 «색이 읽히고 글자가 칸에 드는지», `shot_screen` 은 «사람이 보는 그림». 하나로는
못 덮는다 — 이번에 셋이 각자 다른 결함을 잡았다.

## §4. 오늘 잡힌 것 — 다음 사람이 같은 길로 안 가게

1. **번들이 새는 길은 임포트 한 줄이다.** 커브가 상수 하나를 `useLwChart` 에서 가져오자 메인 첫
   화면 JS 가 787KB → 964KB 가 됐다(그 파일이 모듈 꼭대기에서 라이브러리를 부른다). 수를 들고
   있는 파일은 **아무것도 안 물어야** 한다 → `chart/metrics.ts`. 가드가 잰다.
2. **대비는 «색» 이 아니라 «어느 면 위인가» 다.** 같은 뮤트 글자가 카드 위에서 5.87, 컨트롤 면
   위에서 4.47 이었다. 프로브가 이제 떨어지는 면을 같이 적는다.
3. **그래픽은 채움색을 재야 한다.** 상태 점의 «글자색» 을 재고 1.86:1 이라 보고했었다 — 그건
   잉크 대 청록이었고 아무 뜻이 없는 수였다.
4. **flex 상자 안에서는 글자 사이 공백이 접힌다.** 알약을 flex 로 바꾸자 「첫호가4」가 됐다.
   자로는 안 나오고 눈이 잡았다.
5. **죽은 CSS 는 다음 사람에게 «이 앱의 규칙» 으로 읽힌다.** 아무것도 emit 하지 않는 `.kb-heat`
   때문에 히트맵 CSS 를 두 곳에서 찾았다. 그래서 걷는다(275 규칙).
6. **줄 범위로 자르지 마라.** `type.css` 를 「124줄부터 끝까지」로 자르려다 뒤쪽의
   `.sr-plot`·`.sr-casedash` 까지 잘릴 뻔했다. 선택자로 골라야 한다.
7. **가드도 틀린다 — 셋이 틀렸다.** 줄 단위로 보면 선택자를 놓치고, 판정이 뒤집혀 있었고,
   주석을 못 건너뛰었다. 가드를 쓰면 «일부러 어겨 보고» 빨간지 확인하라.

## §5. 숫자

| | 전 | 후 |
|---|---|---|
| 지문 대조 | 0건 | **0건**(값은 한 자리도 안 바뀌었다) |
| probe 위반(대비·넘침) | 33건 | **0건** |
| guards | 0개 | **126개** |
| 서식 도우미 | 6벌(표류) | 1벌 |
| 눈금 알고리즘 | 3 | 1 |
| 방향색 오용 | 5곳 | 0 |
| 폭 없는 표 | 5 | 0 |
| `type.css` | 86,064B | 15,154B |
| 첫 화면 정적 | 1,638,574B | 1,633,672B |
| 국고 탭 추가 | 0B | 192,646B(lightweight-charts, 지연 로드) |

## §6. 남은 것 · 오너 판정

- **십자선 가격 칩 정밀도** — 지금 축과 같은 2자리. 3자리로 하면 눈금도 3자리가 된다.
- **`ActBin.tot`** — 서버의 «척도용 합계». 화면은 이제 `n/max(n)` 을 쓴다(옛 판의 버그를 고쳤다).
  payload 에서 뺄지는 백엔드 몫.
- **옛 화면(`/`)** — 토스 문법 그대로다. 이 레인은 새 화면(`/app`)만 건드렸다.
- **`.kb-ch-ctl`** — 정의만 있고 아직 쓰는 카드가 없다(머리에 컨트롤이 붙는 카드가 생기면 쓴다).
- ~~Vercel 배포~~ **닫힘** — 오너가 09-28 직접 배포(`dpl_2H3BkjP8…` · `kbond-web.vercel.app` 별칭).
  라이브에서 확인: 첫 화면 청크 열 중 **lightweight-charts 를 문 것 0개**(지연 로드가 프로덕션
  에서도 먹었다) · 스트립 CSS 있음 · dyn 조각 200 · 옛 통짜 글꼴 404.
  세션 안에서는 배포 명령이 차단되므로 앞으로도 오너 몫이다.

## §7. 손댄 파일

```
kbond-web
  src/chart/*        v2 이식 + metrics·activityBars·StackChart 신설
  src/ui/            Delta · ColGroup · ChartReadoutStrip(v2) · useMeasure(v2)
  src/lib/           format.ts · tint.ts · columns.ts 신설
  src/components/    PxChart·PulseChart 신설 · Bonds·Credit·Trends·Feed·Heat·Curve·Setup 수정
  src/theme/         type.css 86→15KB · kbond.css 전면
  guards/            _source·setup(v2) · color-source·motion-tokens·no-midword-break(v2) ·
                     format-single-source·chart-canon·design-canon 신설 (126 시험)
kbond
  compare_screens.mjs  부호 정규화 · 잔존 허용 · 넘침 접기
  probe_screen.mjs     ★신설 — 대비·넘침·CH_PX
  measure_load.mjs     ★신설 — 첫 화면이 실제로 받는 바이트
```

---

## §8. 이 문법 위에 지은 기능은 따로 본다

[OWNER 2026-09-28 저녁] 「트레이더 입장에서 쓸 수 있는게 잘 없어」로 **커브반영 · 또래 순위 ·
「싼 것부터」** 를 지었다. 그것은 문법이 아니라 기능이라 정본이 따로 있다 —
**`PROMPT_next_2026-09-28-trader.md`**. 이 문서와 겹치는 자리는 둘뿐이다:

- §2 예외 표의 **일곱째**(리드아웃 유휴) — 아래 표에 이미 들어 있다.
- §3 검증 레시피에 한 줄 더 — 새 배지·새 칸을 냈으면 **지문 창(첫 15줄) 안에 그것이 들어오게
  해 놓고** 돌린다. 「1위」 배지가 창 밖에 있어서 지문이 «운으로» 0건을 낸 전례가 있다
  (trader 정본 §5-3).
