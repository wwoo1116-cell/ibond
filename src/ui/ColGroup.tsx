/**
 * 표의 열 폭을 «한 곳에서» 준다. [2026-09-28]
 *
 * `table-layout: fixed` 는 첫 행(또는 `<colgroup>`)의 폭을 그대로 쓴다. 폭을 안
 * 주면 남은 폭을 **똑같이** 나누므로, 「나이」 칸이 종목명과 같은 폭을 받고 종목명은
 * 잘린다 — 이 앱의 표 다섯이 그 상태였다.
 *
 * 폭은 `lib/columns.ts` 의 서식 최대치에서 온다. 여기서는 그것을 DOM 에 옮기기만
 * 한다 — 폭을 «정하는 곳» 과 «그리는 곳» 이 갈리면 둘이 어긋난다.
 */
import type { ColSpec } from '@/lib/columns';

export function ColGroup({ cols }: { cols: ColSpec }) {
  return (
    <colgroup>
      {cols.map((w, i) => (
        /* 열은 «자리» 로만 식별된다 — 이름이 없다. */
        <col key={i} style={w == null ? undefined : { width: `${w}px` }} />
      ))}
    </colgroup>
  );
}
