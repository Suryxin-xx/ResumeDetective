import { useEffect, useState } from "react";
import { spacePreferenceKey } from "./api";

export function readView<T>(key: string, fallback: T): T {
  try { return JSON.parse(sessionStorage.getItem(spacePreferenceKey(key)) || "null") ?? fallback; } catch { return fallback; }
}

export function useViewPreference<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(() => readView(key, fallback));
  useEffect(() => { try { sessionStorage.setItem(spacePreferenceKey(key), JSON.stringify(value)); } catch { /* Storage may be disabled. */ } }, [key, value]);
  return [value, setValue] as const;
}

export function usePageScroll(key: string) {
  useEffect(() => {
    const frame = requestAnimationFrame(() => window.scrollTo(0, readView<number>(key, 0)));
    const save = () => { try { sessionStorage.setItem(spacePreferenceKey(key), JSON.stringify(window.scrollY)); } catch { /* Optional preference. */ } };
    window.addEventListener("scroll", save, { passive: true });
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", save); };
  }, [key]);
}
