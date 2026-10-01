import { useEffect, useRef } from "react";
let guard: (() => boolean) | null = null;
export function canNavigate() { return guard?.() ?? true; }
export function useUnsavedChanges(dirty: boolean, busy = false) {
  const state = useRef({ dirty, busy });
  state.current = { dirty, busy };
  useEffect(() => {
    const check = () => {
      if (state.current.busy) { window.alert("正在保存，请稍后再离开。"); return false; }
      return !state.current.dirty || window.confirm("有未保存的修改，确定放弃并离开吗？");
    };
    guard = check;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (state.current.dirty || state.current.busy) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => { if (guard === check) guard = null; window.removeEventListener("beforeunload", beforeUnload); };
  }, []);
}
