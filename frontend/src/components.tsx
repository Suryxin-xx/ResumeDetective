import type { PropsWithChildren, ReactNode } from "react";
import { X } from "lucide-react";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
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

export function Modal({ title, subtitle, onClose, children, wide = false }: PropsWithChildren<{ title: string; subtitle?: string; onClose: () => void; wide?: boolean }>) {
  return (
    <div className="modal-layer" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`modal-card ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-heading">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        </div>
        {children}
      </section>
    </div>
  );
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
  "待研究": "neutral", "暂不考虑": "neutral", "通过": "green", "未通过": "red", "待确认": "neutral",
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
