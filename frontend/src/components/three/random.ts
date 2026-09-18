/**
 * A tiny deterministic PRNG shared by every generated scene layout
 * (CanopyField, Fireflies). Two things this buys over `Math.random()`:
 *
 * - the layout is identical on every load, which matters for
 *   `react-hooks/purity` — a `useMemo` factory calling `Math.random()`
 *   is flagged as impure because the React Compiler cannot prove the
 *   memoised value would be the same if recomputed, whereas a
 *   seed-derived value provably is;
 * - it makes a scene's layout reproducible for debugging without needing
 *   to freeze a random seed some other way.
 */
export function mulberry32(seed: number) {
  let a = seed;
  return function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
