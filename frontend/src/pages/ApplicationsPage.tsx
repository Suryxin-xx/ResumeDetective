import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, FileUp, Filter, Search, Sparkles, Trash2 } from "lucide-react";
import { api, formatDateTime, jsonBody, todayISO } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel, Priority, StatusBadge } from "../components";
import type { PageProps } from "../App";
import type { Application } from "../types";

const statuses = ["已投递", "简历筛选", "测评", "AI 面试", "笔试", "业务面试", "HR 面", "Offer", "终止"];
const stageStates = ["待处理", "已安排", "已完成，等待结果", "已完成"];
const sources = ["官网", "内推", "Boss 直聘", "牛客", "实习转正", "招聘会", "其他"];
const categories = ["研发", "算法", "产品", "设计", "运营", "销售", "供应链", "职能", "其他"];

export default function ApplicationsPage({ data, refresh, go, newSignal, consumeNewSignal }: PageProps & { newSignal: number; consumeNewSignal: () => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("全部");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!newSignal) return;
    setShowNew(true);
    consumeNewSignal();
  }, [newSignal, consumeNewSignal]);

  const filtered = useMemo(() => data.applications.filter((item) => {
    const text = `${item.companyName} ${item.positionName} ${item.tags} ${item.category}`.toLowerCase();
    if (query && !text.includes(query.toLowerCase())) return false;
    if (filter === "全部") return true;
    if (filter === "流程中") return item.currentStatus !== "终止" && item.currentStatus !== "Offer";
    return item.currentStatus === filter;
  }), [data.applications, query, filter]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("resumeFile");
    values.delete("resumeFile");
    const payload = Object.fromEntries(values.entries());
    payload.priority = Number(payload.priority) as never;
    try {
      const result = await api<{ id: number }>("/applications", { method: "POST", ...jsonBody(payload) });
      if (file instanceof File && file.size) await uploadResume(result.id, file);
      setShowNew(false);
      form.reset();
      await refresh();
      setExpanded(result.id);
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "保存失败");
    } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader eyebrow="APPLICATIONS" title="投递管理" description="表格负责扫视，展开行负责处理细节。" />
      <Panel className="filter-panel">
        <div className="filter-row">
          <label className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司、岗位或标签" /></label>
          <div className="segmented" aria-label="状态筛选">
            {["全部", "流程中", "已投递", "简历筛选", "测评", "业务面试", "Offer", "终止"].map((value) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{value}</button>)}
          </div>
          <span className="result-count"><Filter size={14} />{filtered.length} 条</span>
        </div>
      </Panel>
      <Panel className="table-panel">
        {filtered.length ? (
          <div className="data-table-wrap">
            <table className="data-table application-table">
              <thead><tr><th>公司 / 岗位</th><th>当前环节</th><th>环节状态</th><th>投递日期</th><th>状态更新时间</th><th>优先级</th><th aria-label="操作" /></tr></thead>
              <tbody>{filtered.map((item) => (
                <ApplicationRows key={item.id} item={item} expanded={expanded === item.id} onToggle={() => setExpanded(expanded === item.id ? null : item.id)} refresh={refresh} go={go} />
              ))}</tbody>
            </table>
          </div>
        ) : <EmptyState title="没有符合条件的投递" description="换一个筛选条件，或新建一条投递记录。" action={<button className="secondary-button" onClick={() => { setFilter("全部"); setQuery(""); }}>清除筛选</button>} />}
      </Panel>
      {showNew && <Modal title="新建投递" subtitle="默认记录为“已投递”，日期使用今天；之后都可以调整。" onClose={() => setShowNew(false)} wide><ApplicationForm onSubmit={create} onClose={() => setShowNew(false)} busy={busy} /></Modal>}
    </>
  );
}

function ApplicationRows({ item, expanded, onToggle, refresh, go }: { item: Application; expanded: boolean; onToggle: () => void; refresh: () => Promise<void>; go: (page: string) => void }) {
  const [busy, setBusy] = useState(false);
  async function update(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    const file = values.get("resumeFile"); values.delete("resumeFile");
    const payload = Object.fromEntries(values.entries()); payload.priority = Number(payload.priority) as never;
    try {
      await api(`/applications/${item.id}`, { method: "PATCH", ...jsonBody(payload) });
      if (file instanceof File && file.size) await uploadResume(item.id, file);
      await refresh();
    } catch (reason) { window.alert(reason instanceof Error ? reason.message : "更新失败"); }
    finally { setBusy(false); }
  }
  return (
    <>
      <tr className={item.currentStatus === "终止" ? "terminal-row" : ""}>
        <td><div className="entity-cell"><span className="company-avatar">{item.companyName.slice(0, 1)}</span><span><strong>{item.companyName}</strong><small>{item.positionName}{item.city ? ` · ${item.city}` : ""}</small></span></div></td>
        <td><StatusBadge value={item.currentStatus} /></td><td>{item.stageState}</td><td>{item.appliedAt || "—"}</td><td>{formatDateTime(item.statusUpdateTime)}</td><td><Priority value={item.priority} /></td>
        <td><button className="row-toggle" onClick={onToggle}>{expanded ? <>收起 <ChevronUp size={15} /></> : <>管理 <ChevronDown size={15} /></>}</button></td>
      </tr>
      {expanded && <tr className="expanded-row"><td colSpan={7}><form className="inline-editor" onSubmit={update}>
        <div className="editor-summary"><div><span className="eyebrow">APPLICATION #{item.id}</span><h3>{item.companyName} · {item.positionName}</h3><p>{item.jdText ? item.jdText.slice(0, 180) : "尚未保存 JD，建议在岗位关闭前补充。"}</p></div><div className="editor-quick-actions"><button type="button" className="secondary-button" onClick={() => go("ai")}><Sparkles size={15} />AI 准备</button>{item.jobLink && <a className="secondary-button" href={item.jobLink} target="_blank" rel="noreferrer">岗位链接 <ExternalLink size={14} /></a>}{item.resumePath && <a className="secondary-button" href={`/resume/${item.id}`} target="_blank" rel="noreferrer">查看简历 <ExternalLink size={14} /></a>}</div></div>
        <div className="editor-grid">
          <Field label="当前环节"><select name="currentStatus" defaultValue={item.currentStatus}>{statuses.map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Field label="环节状态"><select name="stageState" defaultValue={item.stageState}>{stageStates.map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Field label="下一步行动"><input name="nextAction" defaultValue={item.nextAction} list="next-actions" placeholder="例如：等待结果 / 准备业务面" /></Field>
          <Field label="优先级"><select name="priority" defaultValue={item.priority}>{[0, 1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value ? `${value} 级` : "普通"}</option>)}</select></Field>
          <Field label="城市"><input name="city" defaultValue={item.city} /></Field>
          <Field label="投递来源"><input name="source" defaultValue={item.source} list="sources" /></Field>
          <Field label="岗位类型"><input name="category" defaultValue={item.category} list="categories" /></Field>
          <Field label="自定义标签"><input name="tags" defaultValue={item.tags} placeholder="供应链, 新能源, 管培" /></Field>
          <Field label="岗位链接" span><input name="jobLink" type="url" defaultValue={item.jobLink} /></Field>
          <Field label="投递日期"><input name="appliedAt" type="date" defaultValue={item.appliedAt} /></Field>
          <Field label="绑定或替换简历"><input name="resumeFile" type="file" accept=".pdf,.doc,.docx" /></Field>
          <Field label="JD 原文" hint="岗位关闭后仍保留，AI 分析也会以此为依据。" span><textarea name="jdText" rows={7} defaultValue={item.jdText} /></Field>
          <input type="hidden" name="applicationDeadline" value={item.applicationDeadline} /><input type="hidden" name="nextActionDueAt" value={item.nextActionDueAt} /><input type="hidden" name="lastFollowUpAt" value={item.lastFollowUpAt} />
        </div>
        <div className="history-block"><h4>流转详情</h4>{item.statusHistory.length ? <ol>{item.statusHistory.slice().reverse().map((event, index) => <li key={`${event.time}-${index}`}><span /><div><strong>{event.from ? `${event.from} → ${event.to}` : event.to}</strong><small>{formatDateTime(event.time)}{event.note ? ` · ${event.note}` : ""}</small></div></li>)}</ol> : <p className="muted-text">暂无流转记录</p>}</div>
        <div className="editor-actions"><ConfirmButton confirmText={`确定删除 ${item.companyName} · ${item.positionName}？数据库记录会删除，绑定文件仍保留。`} onConfirm={async () => { await api(`/applications/${item.id}`, { method: "DELETE" }); await refresh(); }}><Trash2 size={15} />删除投递</ConfirmButton><button className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存修改"}</button></div>
      </form></td></tr>}
    </>
  );
}

function ApplicationForm({ onSubmit, onClose, busy }: { onSubmit: (event: React.FormEvent<HTMLFormElement>) => void; onClose: () => void; busy: boolean }) {
  return <form onSubmit={onSubmit}><div className="modal-form-grid">
    <Field label="公司名称"><input name="companyName" required autoFocus placeholder="例如：华为" /></Field>
    <Field label="岗位名称"><input name="positionName" required placeholder="例如：硬件技术工程师" /></Field>
    <Field label="当前环节"><select name="currentStatus" defaultValue="已投递">{statuses.map((value) => <option key={value}>{value}</option>)}</select></Field>
    <Field label="环节状态"><select name="stageState" defaultValue="已完成，等待结果">{stageStates.map((value) => <option key={value}>{value}</option>)}</select></Field>
    <Field label="投递日期"><input name="appliedAt" type="date" defaultValue={todayISO()} /></Field>
    <Field label="优先级"><select name="priority" defaultValue="0">{[0, 1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value ? `${value} 级` : "普通"}</option>)}</select></Field>
    <Field label="城市"><input name="city" placeholder="上海" /></Field>
    <Field label="投递来源"><input name="source" list="sources" placeholder="官网 / 内推" /></Field>
    <Field label="岗位类型"><input name="category" list="categories" placeholder="研发 / 供应链 / 产品" /></Field>
    <Field label="自定义标签"><input name="tags" placeholder="新能源, 管培" /></Field>
    <Field label="岗位链接" span><input name="jobLink" type="url" placeholder="https://" /></Field>
    <Field label="绑定简历" span><input name="resumeFile" type="file" accept=".pdf,.doc,.docx" /></Field>
    <Field label="JD 原文" hint="建议完整保存，后续复盘和 AI 分析都会用到。" span><textarea name="jdText" rows={7} /></Field>
    <input type="hidden" name="nextAction" value="等待结果" /><input type="hidden" name="applicationDeadline" value="" /><input type="hidden" name="nextActionDueAt" value="" /><input type="hidden" name="lastFollowUpAt" value="" />
  </div><div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存投递"}</button></div>
  <datalist id="sources">{sources.map((value) => <option key={value} value={value} />)}</datalist><datalist id="categories">{categories.map((value) => <option key={value} value={value} />)}</datalist><datalist id="next-actions">{["等待结果", "完成测评", "准备笔试", "准备业务面", "准备 HR 面", "跟进进度", "接受 Offer"].map((value) => <option key={value} value={value} />)}</datalist></form>;
}

async function uploadResume(id: number, file: File) {
  const body = new FormData(); body.append("resume", file);
  await api(`/applications/${id}/resume`, { method: "POST", body });
}
