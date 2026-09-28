/**
 * 변화 한 칸 — **네 부품 한 벌**. [2026-09-28, v2 캐논 「변화 셀」]
 *
 * v2 는 변화를 네 부품으로 적는다: 틴트 배경 · 방향 클래스 · 화살표 글리프 ·
 * 부호 없는 숫자. 넷이 한 벌인 이유는 **한 화면에서 같은 양이 두 어휘로
 * 말해지지 않게** 하기 위해서다 — 어제까지 이 앱은 자리마다 `+1.5bp`·`-17.5bp`·
 * `+0.0` 를 제각기 조립하고 있었고, 그중 하나는 `bp` 를 두 번 붙였다.
 *
 * 여기서 «값» 은 화살표 + 숫자다. 색은 그 둘을 **보강**할 뿐이라, 색을 못 보는
 * 눈으로도 방향이 읽힌다(WCAG 1.4.1).
 *
 * ⚠지문 계약 — 이 원소는 늘 **기존 칸 안에** 중첩된다(형제로 두지 않는다).
 *   `compare_screens` 가 `.kb-li.cr` 의 자식 넷과 `.kb-li2` 의 자식 넷을 차례로
 *   읽으므로, 칸을 하나 더 만들면 값이 안 바뀌었는데 지문이 어긋난다.
 */
import { directionClass, directionGlyph, unsignedDelta } from '@/lib/tint';
import { EMDASH, fmtSigned } from '@/lib/format';

export function Delta({
  v,
  unit = '',
  digits = 1,
  ink = false,
}: {
  v?: number | null;
  /** 숫자 뒤에 붙는 단위 — `bp` · `원` · `%`. 열 머리가 이미 말하면 비운다. */
  unit?: string;
  digits?: number;
  /**
   * 글자를 방향색이 아니라 **잉크**로 둔다.
   *
   * 틴트가 칠해진 칸에서 켠다 — 같은 부호 틴트 위의 방향색 글자는 어느 농도에서도
   * 4.5:1 을 못 넘는다(30%에서 3.0 · 42%에서 2.5 · 62%에서 1.8, v2 `theme/tint.ts`
   * 실측). 농도 조절 문제가 아니라 범주적 규칙이라 스위치로 둔다.
   */
  ink?: boolean;
}) {
  const glyph = directionGlyph(v);
  const body = v == null ? EMDASH : `${unsignedDelta(fmtSigned(v, digits))}${unit}`;
  return (
    <span className={ink ? 'kb-delta' : `kb-delta ${directionClass(v)}`}>
      {glyph ? `${glyph} ` : ''}
      {body}
    </span>
  );
}
