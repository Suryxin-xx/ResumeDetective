import { useEffect, useMemo, useState } from "react";
import { CheckSquare2, ChevronDown, ChevronUp, Download, ExternalLink, Eye, EyeOff, FileText, Filter, ImageDown, Link2, Search, Sparkles, Trash2 } from "lucide-react";
import { api, formatDateTime, jsonBody, todayISO } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel, Priority, StatusBadge } from "../components";
import type { PageProps } from "../App";
import type { Application } from "../types";

const statuses = ["已投递", "简历筛选", "测评", "AI 面试", "笔试", "业务面试", "HR 面", "Offer", "终止"];
const stageStates = ["待处理", "已安排", "已完成，等待结果", "已完成"];
const sources = ["官网", "内推", "Boss 直聘", "牛客", "实习转正", "招聘会", "其他"];
const categories = ["研发", "算法", "产品", "设计", "运营", "销售", "供应链", "职能", "其他"];
const terminalStatuses = new Set(["终止", "已终止", "未通过", "主动放弃", "流程结束"]);
const groupedStatuses: Record<string, string[]> = { "投递与初筛": ["已投递", "简历筛选"], "测评与笔试": ["测评", "AI 面试", "笔试"], "面试阶段": ["业务面试", "HR 面"] };
function hashSelection() { const params = new URLSearchParams(window.location.hash.split("?")[1] || ""); return { status: params.get("status") || "", application: Number(params.get("application") || 0) }; }

export default function ApplicationsPage({ data, refresh, go, newSignal, consumeNewSignal }: PageProps & { newSignal: number; consumeNewSignal: () => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(() => hashSelection().status || "全部");
  const [categoryFilter, setCategoryFilter] = useState("全部类型");
  const [sort, setSort] = useState("updated");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hideTerminal, setHideTerminal] = useState(() => localStorage.getItem("applications-hide-terminal") !== "false");
  useEffect(() => {
    if (!newSignal) return;
    setShowNew(true);
    consumeNewSignal();
  }, [newSignal, consumeNewSignal]);
  useEffect(() => localStorage.setItem("applications-hide-terminal", String(hideTerminal)), [hideTerminal]);
  useEffect(() => {
    const syncHash = () => { const selection = hashSelection(); if (selection.status) setFilter(selection.status); if (selection.application) { setFilter("全部"); setExpanded(selection.application); requestAnimationFrame(() => document.getElementById(`application-${selection.application}`)?.scrollIntoView({ behavior: "smooth", block: "center" })); } };
    syncHash(); window.addEventListener("hashchange", syncHash); return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  const filtered = useMemo(() => data.applications.filter((item) => {
    const text = `${item.companyName} ${item.positionName} ${item.tags} ${item.category}`.toLowerCase();
    if (query && !text.includes(query.toLowerCase())) return false;
    if (categoryFilter !== "全部类型" && item.category !== categoryFilter) return false;
    if (hideTerminal && filter !== "终止" && terminalStatuses.has(item.currentStatus)) return false;
    if (filter === "全部") return true;
    if (filter === "流程中") return !terminalStatuses.has(item.currentStatus) && item.currentStatus !== "Offer";
    if (groupedStatuses[filter]) return groupedStatuses[filter].includes(item.currentStatus);
    return filter === "终止" ? terminalStatuses.has(item.currentStatus) : item.currentStatus === filter;
  }).sort((a,b)=>{ const terminalOrder=Number(terminalStatuses.has(a.currentStatus))-Number(terminalStatuses.has(b.currentStatus)); if(terminalOrder)return terminalOrder; return sort==="company"?a.companyName.localeCompare(b.companyName,"zh-CN"):sort==="priority"?b.priority-a.priority:new Date(b.statusUpdateTime).getTime()-new Date(a.statusUpdateTime).getTime(); }), [data.applications, query, filter, categoryFilter, sort, hideTerminal]);
  const categoryOptions=useMemo(()=>["全部类型",...Array.from(new Set(data.applications.map(item=>item.category).filter(Boolean)))],[data.applications]);
  const selectedItems=filtered.filter(item=>selected.has(item.id));
  const toggleSelected=(id:number)=>setSelected(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next});

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
      setFilter("全部");
      setExpanded(result.id);
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "保存失败");
    } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="投递管理" description="高密度扫视、就地编辑；可批量导出或生成适合分享的脱敏图片。" />
      <Panel className="filter-panel">
        <div className="filter-row">
          <label className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司、岗位或标签" /></label>
          <div className="segmented" aria-label="状态筛选">
            {["全部", "流程中", "已投递", "简历筛选", "测评与笔试", "面试阶段", "Offer", "终止"].map((value) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{value}</button>)}
          </div>
          <select className="compact-select" value={categoryFilter} onChange={event=>setCategoryFilter(event.target.value)}>{categoryOptions.map(value=><option key={value}>{value}</option>)}</select>
          <select className="compact-select" value={sort} onChange={event=>setSort(event.target.value)}><option value="updated">最近更新</option><option value="priority">优先级</option><option value="company">公司名称</option></select>
          <button type="button" className={`terminal-toggle ${hideTerminal ? "active" : ""}`} onClick={()=>setHideTerminal(value=>!value)}>{hideTerminal?<EyeOff size={14}/>:<Eye size={14}/>} {hideTerminal?"已隐藏终止":"显示终止"}</button>
          <span className="result-count"><Filter size={14} />{filtered.length} 条</span>
        </div>
      </Panel>
      {selectedItems.length>0&&<div className="bulk-toolbar"><span><CheckSquare2 size={16}/>已选择 <strong>{selectedItems.length}</strong> 条</span><button className="secondary-button" onClick={()=>exportApplicationsCSV(selectedItems)}><Download size={15}/>导出 CSV</button><button className="secondary-button" onClick={()=>void exportApplicationsImage(selectedItems)}><ImageDown size={15}/>生成分享图</button><button className="text-button" onClick={()=>setSelected(new Set())}>取消选择</button></div>}
      <Panel className="table-panel">
        {filtered.length ? (
          <div className="data-table-wrap">
            <table className="data-table application-table">
              <thead><tr><th className="check-column"><input type="checkbox" aria-label="全选当前结果" checked={filtered.length>0&&filtered.every(item=>selected.has(item.id))} onChange={event=>setSelected(event.target.checked?new Set(filtered.map(item=>item.id)):new Set())}/></th><th>公司 / 岗位</th><th>当前环节</th><th>环节状态</th><th>投递日期</th><th>状态更新时间</th><th>优先级</th><th aria-label="操作" /></tr></thead>
              <tbody>{filtered.map((item) => (
                <ApplicationRows key={item.id} item={item} selected={selected.has(item.id)} onSelect={()=>toggleSelected(item.id)} expanded={expanded === item.id} onToggle={() => setExpanded(expanded === item.id ? null : item.id)} refresh={refresh} go={go} />
              ))}</tbody>
            </table>
          </div>
        ) : <EmptyState title="没有符合条件的投递" description="换一个筛选条件，或新建一条投递记录。" action={<button className="secondary-button" onClick={() => { setFilter("全部"); setQuery(""); }}>清除筛选</button>} />}
      </Panel>
      {showNew && <Modal title="新建投递" subtitle="默认记录为“已投递”，日期使用今天；之后都可以调整。" onClose={() => setShowNew(false)} wide><ApplicationForm onSubmit={create} onClose={() => setShowNew(false)} busy={busy} /></Modal>}
    </>
  );
}

function ApplicationRows({ item, selected, onSelect, expanded, onToggle, refresh, go }: { item: Application; selected:boolean; onSelect:()=>void; expanded: boolean; onToggle: () => void; refresh: () => Promise<void>; go: (page: string) => void }) {
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
      <tr id={`application-${item.id}`} className={`${terminalStatuses.has(item.currentStatus) ? "terminal-row" : ""} status-row-${item.currentStatus.replace(/\s/g,'-')}`}>
        <td className="check-column"><input type="checkbox" checked={selected} onChange={onSelect} aria-label={`选择 ${item.companyName} ${item.positionName}`}/></td>
        <td><div className="entity-cell"><span className="company-avatar">{item.companyName.slice(0, 1)}</span><span><strong>{item.companyName}</strong><small>{item.positionName}{item.city ? ` · ${item.city}` : ""}</small></span></div></td>
        <td><StatusBadge value={item.currentStatus} /></td><td>{item.stageState}</td><td>{item.appliedAt || "—"}</td><td>{formatDateTime(item.statusUpdateTime)}</td><td><Priority value={item.priority} /></td>
        <td><div className="row-actions">{item.jobLink&&<a className="icon-button" href={item.jobLink} target="_blank" rel="noreferrer" title="打开岗位链接" aria-label="打开岗位链接"><Link2 size={14}/></a>}{item.resumePath&&<a className="icon-button" href={`/resume/${item.id}`} target="_blank" rel="noreferrer" title="直接打开简历" aria-label="直接打开简历"><FileText size={14}/></a>}<button className="row-toggle" onClick={onToggle}>{expanded ? <>收起 <ChevronUp size={15} /></> : <>管理 <ChevronDown size={15} /></>}</button></div></td>
      </tr>
      {expanded && <tr className="expanded-row"><td colSpan={8}><form className="inline-editor" onSubmit={update}>
        <div className="editor-summary"><div><span className="eyebrow">APPLICATION #{item.id}</span><h3>{item.companyName} · {item.positionName}</h3><p>{item.jdText ? item.jdText.slice(0, 180) : "尚未保存 JD，建议在岗位关闭前补充。"}</p></div><div className="editor-quick-actions"><button type="button" className="secondary-button" onClick={() => go(`ai?application=${item.id}`)}><Sparkles size={15} />岗位准备</button>{item.jobLink && <a className="secondary-button" href={item.jobLink} target="_blank" rel="noreferrer">岗位链接 <ExternalLink size={14} /></a>}{item.resumePath && <a className="secondary-button" href={`/resume/${item.id}`} target="_blank" rel="noreferrer">查看简历 <ExternalLink size={14} /></a>}</div></div>
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
          <Field label="JD 原文" hint="岗位关闭后仍保留，岗位准备助手也会以此为依据。" span><textarea name="jdText" rows={7} defaultValue={item.jdText} /></Field>
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

function exportApplicationsCSV(items:Application[]){
  const rows=[["公司","岗位","类型","城市","投递来源","当前环节","环节状态","投递日期","状态更新时间"],...items.map(item=>[item.companyName,item.positionName,item.category,item.city,item.source,item.currentStatus,item.stageState,item.appliedAt,item.statusUpdateTime])];
  const csv="\uFEFF"+rows.map(row=>row.map(value=>`"${String(value||"").replace(/"/g,'""')}"`).join(",")).join("\r\n");downloadBlob(new Blob([csv],{type:"text/csv;charset=utf-8"}),`投递记录-${todayISO()}.csv`);
}
async function exportApplicationsImage(items:Application[]){
  const width=1200,rowHeight=66,height=170+Math.min(items.length,20)*rowHeight;const canvas=document.createElement("canvas");canvas.width=width;canvas.height=height;const ctx=canvas.getContext("2d");if(!ctx)return;
  ctx.fillStyle="#f5f7fb";ctx.fillRect(0,0,width,height);ctx.fillStyle="#111827";ctx.font="700 34px 'Microsoft YaHei',sans-serif";ctx.fillText("求职投递进度",56,62);ctx.fillStyle="#64748b";ctx.font="16px 'Microsoft YaHei',sans-serif";ctx.fillText(`${todayISO()} · 共 ${items.length} 条（仅展示前 20 条）`,56,96);
  items.slice(0,20).forEach((item,index)=>{const y=126+index*rowHeight;ctx.fillStyle="#ffffff";ctx.fillRect(40,y,width-80,rowHeight-8);ctx.fillStyle="#182230";ctx.font="700 18px 'Microsoft YaHei',sans-serif";ctx.fillText(item.companyName,60,y+27);ctx.fillStyle="#667085";ctx.font="14px 'Microsoft YaHei',sans-serif";ctx.fillText(item.positionName,260,y+27);ctx.fillStyle="#4f46e5";ctx.fillText(item.currentStatus,700,y+27);ctx.fillStyle="#667085";ctx.fillText(item.category||"未分类",855,y+27);ctx.fillText(item.appliedAt||"—",1000,y+27)});
  const blob=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,"image/png"));if(blob)downloadBlob(blob,`投递进度分享图-${todayISO()}.png`);
}
function downloadBlob(blob:Blob,name:string){const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
