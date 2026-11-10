import { useCallback, useEffect, useState } from 'react';

export type SortDir = 'asc' | 'desc';
export type SortValue = string | number | null | undefined;

// "S2" < "S10", case-insensitive
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

export function compareValues(a: SortValue, b: SortValue): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return collator.compare(String(a), String(b));
}

/** Sort a copy of `rows` by `get(row)`; empty values always go last. */
export function sortRows<T>(rows: T[], get: (row: T) => SortValue, dir: SortDir): T[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((x, y) => {
    const a = get(x);
    const b = get(y);
    const aEmpty = a === null || a === undefined || a === '';
    const bEmpty = b === null || b === undefined || b === '';
    if (aEmpty || bEmpty) return aEmpty === bEmpty ? 0 : aEmpty ? 1 : -1;
    return sign * compareValues(a, b);
  });
}

/** Sort column + direction, remembered per page in localStorage. Clicking the
 *  active column flips the direction; a new column starts ascending. */
export function useSort<K extends string>(storageKey: string, initialKey: K, initialDir: SortDir = 'asc') {
  const [state, setState] = useState<{ key: K; dir: SortDir }>({ key: initialKey, dir: initialDir });

  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) setState(JSON.parse(saved));
    } catch { /* storage unavailable: keep defaults */ }
  }, [storageKey]);

  const toggle = useCallback((key: K) => {
    setState((prev) => {
      const next = { key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' as SortDir : 'asc' as SortDir };
      try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }, [storageKey]);

  return { sortKey: state.key, sortDir: state.dir, toggleSort: toggle };
}
