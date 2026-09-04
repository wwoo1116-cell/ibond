'use client';

/** 백엔드에 닿지 않을 때만 나온다. 주소·토큰은 이 브라우저에만 저장된다. */
import { useState } from 'react';

import { Box, VStack } from '@coinbase/cds-web/layout';
import { Text } from '@coinbase/cds-web/typography';
import { Button } from '@coinbase/cds-web/buttons';
import { TextInput } from '@coinbase/cds-web/controls';

export function Setup({
  defaultBase,
  onDone,
}: {
  defaultBase: string;
  onDone: (base: string, tok: string) => void;
}) {
  const [base, setBase] = useState(defaultBase);
  const [tok, setTok] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  async function connect() {
    const b = base.trim().replace(/\/+$/, '');
    if (!/^https?:\/\//.test(b)) {
      setErr('주소는 https:// 로 시작해야 합니다.');
      return;
    }
    setBusy(true);
    setErr('확인 중…');
    try {
      const r = await fetch(b + '/health' + (tok ? `?t=${encodeURIComponent(tok)}` : ''), {
        cache: 'no-store',
      });
      if (!r.ok) throw new Error(String(r.status));
      const d = (await r.json()) as { uptime_s?: number };
      /* 토큰을 넣었는데 상세가 안 오면 그 토큰이 틀린 것이다(서버가 토큰을 안 쓰면 상세가 온다) */
      if (tok && d.uptime_s === undefined) {
        setErr('토큰이 맞지 않습니다.');
        return;
      }
      onDone(b, tok);
    } catch {
      setErr('서버에 닿지 않습니다. PC 가 켜져 있어야 합니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      display="flex"
      alignItems="center"
      justifyContent="center"
      height="100vh"
      paddingX={4}
    >
      <VStack gap={3} padding={5} width="100%" maxWidth={460}>
        <Text as="h1" font="title3">
          K-Bond 라이브
        </Text>
        <Text as="p" font="body" color="fgMuted">
          책은 내 PC 에서 돕니다. 지금 그 서버에 닿지 않습니다 — PC 가 꺼져 있거나 주소가
          다릅니다. 아래 값은 이 브라우저에만 저장됩니다.
        </Text>
        <TextInput label="서버 주소" value={base} onChange={(e) => setBase(e.target.value)} spellCheck={false} />
        <TextInput
          label="토큰 (없으면 비워 두세요)"
          type="password"
          value={tok}
          onChange={(e) => setTok(e.target.value)}
        />
        <Button onClick={connect} disabled={busy}>
          연결
        </Button>
        {err ? (
          <Text as="p" font="legal" className="sr-up">
            {err}
          </Text>
        ) : null}
      </VStack>
    </Box>
  );
}
