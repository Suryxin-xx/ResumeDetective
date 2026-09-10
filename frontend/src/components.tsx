import { useInsertionEffect, useLayoutEffect, useRef, type PropsWithChildren, type ReactNode } from "react";
import { X } from "lucide-react";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action && <div className="page-action">{action}</div>}
    </header>
  );
}

export function Panel({ title, description, action, children, className = "" }: PropsWithChildren<{ title?: string; description?: string; action?: ReactNode; className?: string }>) {
  return (
    <section className={`panel ${className}`}>
      {(title || description || action) && (
        <div className="panel-heading">
          <div>{title && <h2>{title}</h2>}{description && <p>{description}</p>}</div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

const focusableSelector = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "object",
  "embed",
  "[contenteditable=true]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) => !element.hidden && element.getAttribute("aria-hidden") !== "true" && element.getClientRects().length > 0,
  );
}

export function Modal({ title, subtitle, onClose, children, wide = false }: PropsWithChildren<{ title: string; subtitle?: string; onClose: () => void; wide?: boolean }>) {
  const dialogRef = useRef<HTMLElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Capture the opener before descendants with autoFocus run during the commit.
  useInsertionEffect(() => {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }, []);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    if (dialog) {
      const firstFocusable = getFocusableElements(dialog)[0];
      (firstFocusable ?? dialog).focus({ preventScroll: true });
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab" || !dialog) return;

      const focusableElements = getFocusableElements(dialog);
      if (!focusableElements.length) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }

      const firstFocusable = focusableElements[0];
      const lastFocusable = focusableElements[focusableElements.length - 1];
      if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? lastFocusable : firstFocusable).focus({ preventScroll: true });
      } else if (event.shiftKey && document.activeElement === firstFocusable) {
        event.preventDefault();
        lastFocusable.focus({ preventScroll: true });
      } else if (!event.shiftKey && document.activeElement === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus({ preventScroll: true });
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousBodyOverflow;
      const previousElement = restoreFocusRef.current;
      if (previousElement?.isConnected) previousElement.focus({ preventScroll: true });
    };
  }, []);

  return (
    <div className="modal-layer" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section ref={dialogRef} className={`modal-card ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
        <div className="modal-heading">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        </div>
        {children}
      </section>
    </div>
  );
}

export function Drawer({ title, subtitle, onClose, children }: PropsWithChildren<{ title: string; subtitle?: string; onClose: () => void }>) {
  const dialogRef = useRef<HTMLElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useInsertionEffect(() => {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }, []);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (dialog) (getFocusableElements(dialog)[0] ?? dialog).focus({ preventScroll: true });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = getFocusableElements(dialog);
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    document.body.classList.add("drawer-open");
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("drawer-open");
      const previous = restoreFocusRef.current;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);

  return <div className="drawer-layer" role="presentation" onMouseDown={(event)=>event.target===event.currentTarget&&onClose()}>
    <section ref={dialogRef} className="drawer-card" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
      <div className="drawer-heading"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-button" type="button" aria-label="关闭" onClick={onClose}><X size={18}/></button></div>
      <div className="drawer-content">{children}</div>
    </section>
  </div>;
}

export function Field({ label, hint, span = false, children }: PropsWithChildren<{ label: string; hint?: string; span?: boolean }>) {
  return (
    <label className={`field ${span ? "field-span" : ""}`}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-symbol">·</div><h3>{title}</h3><p>{description}</p>{action}</div>;
}

const statusTone: Record<string, string> = {
  "已投递": "blue", "简历筛选": "indigo", "测评": "amber", "AI 面试": "violet", "笔试": "amber",
  "业务面试": "violet", "HR 面": "pink", "Offer": "green", "终止": "neutral", "待投递": "blue",
  "待研究": "neutral", "暂不考虑": "neutral", "通过": "green", "未通过": "red", "待确认": "neutral", "结果待通知": "neutral",
  "待面试": "violet",
};

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge status-${statusTone[value] ?? "neutral"}`}>{value || "未设置"}</span>;
}

export function Priority({ value }: { value: number }) {
  if (!value) return <span className="muted-text">普通</span>;
  return <span className="priority" aria-label={`优先级 ${value}`}>{Array.from({ length: 5 }, (_, index) => <i key={index} className={index < value ? "on" : ""} />)}</span>;
}

export function ConfirmButton({ children, confirmText, onConfirm, className = "danger-button" }: PropsWithChildren<{ confirmText: string; onConfirm: () => void | Promise<void>; className?: string }>) {
  return <button type="button" className={className} onClick={() => window.confirm(confirmText) && void onConfirm()}>{children}</button>;
}
