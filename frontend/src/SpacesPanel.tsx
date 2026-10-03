import { useState } from "react";
import { Archive, DatabaseBackup, FolderOpen, Plus, RotateCcw } from "lucide-react";
import { api, formatDateTime, jsonBody, spaceDownloadURL } from "./api";
import { canNavigate } from "./navigationGuard";
import { Field } from "./components";

export type Space = { id: string; name: string; archived: boolean; createdAt: string };
export type BackupStatus = { checkedAt: string; success: boolean; fileName: string; error?: string; lastSuccessAt?: string; lastSuccessFile?: string };
export type SpacesView = { registry: { activeId: string; pendingId?: string; items: Space[] }; current: Space; recovery: string; backup: BackupStatus };
type Backup = { name: string; size: number; createdAt: string };

export default function SpacesPanel({ view, refresh }: { view: SpacesView | null; refresh: () => Promise<void> }) {
  const [section, setSection] = useState<"manage" | "import" | "backups">("manage");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [rename, setRename] = useState("");
  const [target, setTarget] = useState<Space | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [backups, setBackups] = useState<Backup[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [switching, setSwitching] = useState(false);
  async function run(action: () => Promise<unknown>, success: string) {
    if (busy || switching) return;
    setBusy(true); setMessage("");
    try { await action(); await refresh(); setMessage(success); } catch (e) { setMessage(e instanceof Error ? e.message : "操作失败"); } finally { setBusy(false); }
  }
  async function switchSpace() {
    if (!target || !canNavigate()) return;
    setBusy(true); setSwitching(true); setMessage("正在备份当前空间并准备切换，请勿关闭程序…");
    try {
      const result = await api<{ restarting: boolean }>("/spaces/switch", { method: "POST", ...jsonBody({ id: target.id }) });
      if (!result.restarting) { setTarget(null); setSwitching(false); setBusy(false); return; }
      for (let i = 0; i < 60; i++) {
        await new Promise(resolve => setTimeout(resolve, 500));
        try {
          const response = await fetch("/api/health", { cache: "no-store" });
          const health = await response.json() as { spaceId?: string };
          if (response.ok && health.spaceId === target.id) { window.location.hash = "/overview"; window.location.reload(); return; }
        } catch { /* Controlled restart briefly closes the socket. */ }
      }
      setMessage("切换尚未确认。请重新打开 EXE 或刷新；若目标不可用，程序会保留原空间。不要重复提交。");
    } catch (e) { setMessage(e instanceof Error ? e.message : "切换失败"); setSwitching(false); }
    finally { setBusy(false); }
  }
  if (!view) return <p>正在读取空间…</p>;
  return <div className="spaces-panel">
    {view.recovery && <p className="space-message" role="status">{view.recovery}</p>}
    <div className="space-current"><strong>求职记录按空间独立保存</strong><span>切换会安全重启本机服务；API 与软件设置共用，其他标签页需刷新。</span></div>
    <nav className="space-section-nav" aria-label="空间管理分类">{([["manage", "空间管理"], ["import", "导入空间"], ["backups", "备份恢复"]] as const).map(([id, label]) => <button type="button" key={id} aria-pressed={section === id} className={section === id ? "active" : ""} disabled={busy || switching} onClick={() => setSection(id)}>{label}</button>)}</nav>
    <div className="space-pane" hidden={section !== "manage"}>
    {target && <div className="space-switch-confirm" role="status"><strong>切换到“{target.name}”？</strong><p>先建立当前空间完整备份，再安全重启。没有保存的编辑不会自动保存。</p><div><button className="primary-button" disabled={busy || switching} onClick={() => void switchSpace()}>确认切换</button><button className="secondary-button" disabled={busy || switching} onClick={() => setTarget(null)}>取消</button></div></div>}
    <div className="space-list">{view.registry.items.filter(s => !s.archived || showArchived).map(s => <article key={s.id} className={s.id === view.current.id ? "space-active" : ""}>
      <div>{editing === s.id ? <input aria-label="新的空间名称" maxLength={60} value={rename} onChange={e => setRename(e.target.value)}/> : <><strong>{s.name}</strong><small>{s.id === view.current.id ? "使用中" : s.archived ? "已归档 · 数据仍保留" : s.id === "default" ? "原始数据 · 路径保持不变" : "独立数据空间"}</small></>}</div>
      <div className="space-actions">{editing === s.id ? <><button className="secondary-button" disabled={busy || switching || !rename.trim()} onClick={() => void run(async () => { await api(`/spaces/${s.id}`, { method: "PATCH", ...jsonBody({ name: rename }) }); setEditing(null); }, "空间已重命名。")}>保存名称</button><button className="text-button" disabled={busy || switching} onClick={() => setEditing(null)}>取消</button></> : <><button className="text-button" disabled={busy || switching} onClick={() => { setEditing(s.id); setRename(s.name); }}>重命名</button>{s.id !== view.current.id && !s.archived && <button className="secondary-button" disabled={busy || switching} onClick={() => setTarget(s)}>切换</button>}{s.id !== "default" && s.id !== view.current.id && <button className="text-button" disabled={busy || switching} onClick={() => void run(() => api(`/spaces/${s.id}`, { method: "PATCH", ...jsonBody({ archived: !s.archived }) }), s.archived ? "空间已取消归档。" : "空间已归档，数据未删除。")}>{s.archived ? <RotateCcw size={14}/> : <Archive size={14}/>} {s.archived ? "恢复显示" : "归档"}</button>}</>}</div>
    </article>)}</div>
    <label className="space-toggle"><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)}/>显示归档空间</label>
    <section className="space-create"><h3>创建空白空间</h3><p>例如秋招、春招各用一个空间；创建后不会自动切换。</p><Field label="新空间名称"><input maxLength={60} value={name} onChange={e => setName(e.target.value)} placeholder="例如 2027 春招"/></Field><div className="space-actions"><button className="primary-button" disabled={busy || switching || !name.trim()} onClick={() => void run(async () => { await api("/spaces", { method: "POST", ...jsonBody({ name }) }); setName(""); }, "空白空间已创建，当前空间没有切换。")}><Plus size={15}/>创建空白空间</button></div>
      </section></div>
    <section className="space-pane space-import" hidden={section !== "import"}><h3>从 v4 目录或完整备份导入</h3><Field label="导入后的空间名称"><input maxLength={60} value={name} onChange={e => setName(e.target.value)} placeholder="例如 2027 春招 · 导入"/></Field><p>请先退出来源程序，再复制并迁移到新空间；不修改来源。Python v3 请先创建空白空间，再使用设置中的迁移入口。ZIP 支持本工具生成的完整空间备份，不接受任意压缩包。</p><Field label="来源目录或完整 .space.zip 路径"><input value={source} onChange={e => setSource(e.target.value)} placeholder="D:\\旧版\\data 或 D:\\备份.space.zip"/></Field><div className="space-actions"><button className="secondary-button" disabled={busy || switching} onClick={() => void run(async () => { const result = await api<{ sourceDir: string }>("/spaces/select-directory", { method: "POST", ...jsonBody({}) }); if (result.sourceDir) setSource(result.sourceDir); }, "目录已选择；导入会单独验证。")}><FolderOpen size={15}/>选择目录</button><button className="secondary-button" disabled={busy || switching || !name.trim() || !source.trim()} onClick={() => void run(() => api("/spaces/import", { method: "POST", ...jsonBody({ name, source }) }), "已导入为新空间，原空间没有改动。")}>导入为新空间</button></div>
    </section>
    <section className="space-pane space-backups" hidden={section !== "backups"}><h3>备份“{view.current.name}”</h3><p>包含数据库、简历和附件；不包含 API、软件配置及其他空间。</p><p>{view.backup.checkedAt ? `最近尝试：${formatDateTime(view.backup.checkedAt)} · ${view.backup.success ? "成功" : "失败"}` : "还没有完整空间备份"}{view.backup.error && ` · ${view.backup.error}`}</p>{!view.backup.success && view.backup.lastSuccessAt && <p>最近成功备份：{formatDateTime(view.backup.lastSuccessAt)} · {view.backup.lastSuccessFile}</p>}<div className="space-actions"><button className="secondary-button" disabled={busy || switching} onClick={() => void run(() => api("/backups", { method: "POST", ...jsonBody({}) }), "完整备份已完成。")}><DatabaseBackup size={15}/>立即完整备份</button><button className="text-button" disabled={busy || switching} onClick={() => void run(async () => setBackups(await api<Backup[]>("/spaces/backups")), "")}>查看备份与恢复</button></div>
      {backups && <div className="space-backup-list">{backups.length === 0 && <p>当前空间暂无完整备份。</p>}{[...backups].sort((a,b) => b.createdAt.localeCompare(a.createdAt)).map(b => <div key={b.name}><span><strong>{formatDateTime(b.createdAt)}</strong><small>{b.name} · {(b.size / 1024 / 1024).toFixed(1)} MB</small></span><a className="text-button" href={spaceDownloadURL(b.name)}>导出</a><button className="secondary-button" disabled={busy || switching} onClick={() => void run(() => api("/spaces/import", { method: "POST", ...jsonBody({ name: `${view.current.name} 恢复副本`, backupName: b.name }) }), "备份已恢复为新空间。核对后再切换，当前记录未覆盖。")}>恢复为新空间</button></div>)}</div>}
    </section>
    {message && <p className="space-message" role="status">{message}</p>}
  </div>;
}
