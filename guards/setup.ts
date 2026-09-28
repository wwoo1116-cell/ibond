/**
 * jsdom gaps the components actually depend on.
 *
 * These are STUBS, not implementations, and the distinction matters: they let a
 * component mount so its STRUCTURE can be asserted. Nothing here produces real
 * geometry, so no test may assert a pixel measurement — that is what the browser
 * probes in the reports are for.
 */

if (typeof globalThis.ResizeObserver === 'undefined') {
  // `InstrumentTable` measures its container to drive the column ladder.
  // Never firing is the honest stub: width stays 0, so the ladder falls back to
  // ALL_COLUMNS, which is the state the ladder guard already covers directly.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

if (typeof globalThis.requestAnimationFrame === 'undefined') {
  globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(0), 0) as unknown as number) as typeof requestAnimationFrame;
  globalThis.cancelAnimationFrame = ((id: number) =>
    clearTimeout(id as unknown as NodeJS.Timeout)) as typeof cancelAnimationFrame;
}
