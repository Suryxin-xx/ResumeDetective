import { useEffect, useMemo, useState } from "react";
import { Building2, CalendarClock, CheckSquare2, Download, ExternalLink, Eye, EyeOff, FileText, Filter, FolderArchive, ImageDown, Link2, Search, Sparkles, Trash2, Video, Workflow, Zap } from "lucide-react";
import { api, formatDateTime, jsonBody, todayISO } from "../api";
import { ConfirmButton, Drawer, EmptyState, Field, Modal, PageHeader, Panel, Priority, StatusBadge } from "../components";
import { stageStateChoices, stageStateLabel } from "../applicationProgress";
import { interviewProgressLabel, interviewResultLabel, preferredInterview } from "../interviewProgress";
import { completedTimeLabel, matchesStageTimeFilter, stageTimeLabel, stageTimeRelative, stageTimeTone, stageTimeValue, type StageTimeFilter } from "../stageSchedule";
import type { PageProps } from "../App";
import type { Application, Interview } from "../types";

const statuses = ["已投递", "简历筛选", "测评", "AI 面试", "笔试", "业务面试", "HR 面", "Offer", "终止"];
const sources = ["官网", "内推", "Boss 直聘", "牛客", "实习转正", "招聘会", "其他"];
const categories = ["研发", "算法", "产品", "设计", "运营", "销售", "供应链", "职能", "其他"];
const terminalStatuses = new Set(["终止", "已终止", "未通过", "主动放弃", "流程结束"]);
const groupedStatuses: Record<string, string[]> = { "投递与初筛": ["已投递", "简历筛选"], "测评与笔试": ["测评", "AI 面试", "笔试"], "面试阶段": ["业务面试", "HR 面"] };
type ResumeOption = { applicationId: number; path: string; label: string };
const stageTimeFilters:StageTimeFilter[]=["全部时间","已逾期","今天","未来3天","未来7天","暂无安排"];
function hashSelection() { const params = new URLSearchParams(window.location.hash.split("?")[1] || ""); const time=params.get("time") as StageTimeFilter; return { status: params.get("status") || "", stage: params.get("stage") || "", time:stageTimeFilters.includes(time)?time:"全部时间", sort:params.get("sort")||"updated", application: Number(params.get("application") || 0) }; }

export default function ApplicationsPage({ data, refresh, go, newSignal, consumeNewSignal }: PageProps & { newSignal: number; consumeNewSignal: () => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(() => hashSelection().status || "全部");
  const [categoryFilter, setCategoryFilter] = useState("全部类型");
  const [stageFilter, setStageFilter] = useState(() => hashSelection().stage || "全部进展");
  const [timeFilter, setTimeFilter] = useState<StageTimeFilter>(()=>hashSelection().time);
  const [sort, setSort] = useState(()=>hashSelection().sort);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [detailId, setDetailId] = useState<number | null>(null);
  const [quickId, setQuickId] = useState<number | null>(null);
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
    const syncHash = () => { const selection = hashSelection(); if (selection.status) setFilter(selection.status); if (selection.stage) setStageFilter(selection.stage); setTimeFilter(selection.time); setSort(selection.sort); if (selection.application) { setFilter("全部"); setDetailId(selection.application); requestAnimationFrame(() => document.getElementById(`application-${selection.application}`)?.scrollIntoView({ behavior: "smooth", block: "center" })); } };
    syncHash(); window.addEventListener("hashchange", syncHash); return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  const filtered = useMemo(() => data.applications.filter((item) => {
    const text = `${item.companyName} ${item.positionName} ${item.tags} ${item.category}`.toLowerCase();
    if (query && !text.includes(query.toLowerCase())) return false;
    if (categoryFilter !== "全部类型" && item.category !== categoryFilter) return false;
    if (stageFilter !== "全部进展" && item.stageState !== stageFilter) return false;
    if (!matchesStageTimeFilter(item, timeFilter)) return false;
    if (hideTerminal && filter !== "终止" && terminalStatuses.has(item.currentStatus)) return false;
    if (filter === "全部") return true;
    if (filter === "流程中") return !terminalStatuses.has(item.currentStatus) && item.currentStatus !== "Offer";
    if (groupedStatuses[filter]) return groupedStatuses[filter].includes(item.currentStatus);
    return filter === "终止" ? terminalStatuses.has(item.currentStatus) : item.currentStatus === filter;
  }).sort((a,b)=>{ const terminalOrder=Number(terminalStatuses.has(a.currentStatus))-Number(terminalStatuses.has(b.currentStatus)); if(terminalOrder)return terminalOrder; if(sort==="schedule")return stageTimeValue(a)-stageTimeValue(b)||b.priority-a.priority; return sort==="company"?a.companyName.localeCompare(b.companyName,"zh-CN"):sort==="priority"?b.priority-a.priority:new Date(b.statusUpdateTime).getTime()-new Date(a.statusUpdateTime).getTime(); }), [data.applications, query, filter, categoryFilter, stageFilter, timeFilter, sort, hideTerminal]);
  const categoryOptions=useMemo(()=>["全部类型",...Array.from(new Set(data.applications.map(item=>item.category).filter(Boolean)))],[data.applications]);
  const resumeOptions=useMemo(()=>existingResumeOptions(data.applications),[data.applications]);
  const interviewsByApplication=useMemo(()=>{const map=new Map<number,Interview[]>();for(const interview of data.interviews){const records=map.get(interview.applicationId);if(records)records.push(interview);else map.set(interview.applicationId,[interview]);}return map},[data.interviews]);
  const selectedItems=filtered.filter(item=>selected.has(item.id));
  const toggleSelected=(id:number)=>setSelected(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next});
  const clearFilters=()=>{setQuery("");setFilter("全部");setCategoryFilter("全部类型");setStageFilter("全部进展");setTimeFilter("全部时间");setSort("updated");setHideTerminal(false);setSelected(new Set());setDetailId(null)};

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("resumeFile");
    const existingResumeApplicationID = Number(values.get("existingResumeApplicationId") || 0);
    values.delete("resumeFile");
    values.delete("existingResumeApplicationId");
    const payload = Object.fromEntries(values.entries());
    payload.priority = Number(payload.priority) as never;
    let result: { id: number };
    try {
      result = await api<{ id: number }>("/applications", { method: "POST", ...jsonBody(payload) });
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "投递保存失败");
      setBusy(false);
      return;
    }
    setShowNew(false);
    form.reset();
    setFilter("全部");
    setDetailId(result.id);
    if (existingResumeApplicationID > 0) {
      try {
        await linkExistingResume(result.id, existingResumeApplicationID);
      } catch (reason) {
        window.alert(`投递已保存，但已有简历关联失败：${reason instanceof Error ? reason.message : "请稍后在投递详情中重新关联"}`);
      }
    } else if (file instanceof File && file.size) {
      try {
        await uploadResume(result.id, file);
      } catch (reason) {
        window.alert(`投递已保存，但简历绑定失败：${reason instanceof Error ? reason.message : "请稍后在投递详情中重新绑定"}`);
      }
    }
    await refresh();
    setBusy(false);
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
          <select className="compact-select" value={stageFilter} onChange={event=>setStageFilter(event.target.value)}><option>全部进展</option>{stageStateChoices("").map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}<option value="已完成">本环节已结束</option></select>
          <select className="compact-select" value={timeFilter} onChange={event=>setTimeFilter(event.target.value as StageTimeFilter)}>{stageTimeFilters.map(value=><option key={value}>{value}</option>)}</select>
          <select className="compact-select" value={sort} onChange={event=>setSort(event.target.value)}><option value="updated">最近更新</option><option value="schedule">环节时间最近</option><option value="priority">优先级</option><option value="company">公司名称</option></select>
          <button type="button" className={`terminal-toggle ${hideTerminal ? "active" : ""}`} onClick={()=>setHideTerminal(value=>!value)}>{hideTerminal?<EyeOff size={14}/>:<Eye size={14}/>} {hideTerminal?"已隐藏终止":"显示终止"}</button>
          <span className="result-count"><Filter size={14} />{filtered.length} 条</span>
        </div>
      </Panel>
      {selectedItems.length>0&&<div className="bulk-toolbar"><span><CheckSquare2 size={16}/>已选择 <strong>{selectedItems.length}</strong> 条</span><button className="secondary-button" onClick={()=>exportApplicationsCSV(selectedItems)}><Download size={15}/>导出 CSV</button><button className="secondary-button" onClick={()=>void exportApplicationsImage(selectedItems)}><ImageDown size={15}/>生成分享图</button><button className="text-button" onClick={()=>setSelected(new Set())}>取消选择</button></div>}
      <Panel className="table-panel">
        {filtered.length ? (
          <div className="data-table-wrap">
            <table className="data-table application-table">
              <thead><tr><th className="check-column"><input type="checkbox" aria-label="全选当前结果" checked={filtered.length>0&&filtered.every(item=>selected.has(item.id))} onChange={event=>setSelected(event.target.checked?new Set(filtered.map(item=>item.id)):new Set())}/></th><th>公司 / 岗位</th><th>当前环节</th><th>环节状态</th><th>环节时间</th><th>投递日期</th><th>状态更新时间</th><th>优先级</th><th aria-label="操作" /></tr></thead>
              <tbody>{filtered.map((item) => (
                <ApplicationRow key={item.id} item={item} interviews={interviewsByApplication.get(item.id)||[]} selected={selected.has(item.id)} onSelect={()=>toggleSelected(item.id)} onQuick={()=>setQuickId(item.id)} onDetails={()=>setDetailId(item.id)} />
              ))}</tbody>
            </table>
          </div>
        ) : <EmptyState title="没有符合条件的投递" description="换一个筛选条件，或新建一条投递记录。" action={<button className="secondary-button" onClick={clearFilters}>清除全部筛选</button>} />}
      </Panel>
      {quickId&&data.applications.find(item=>item.id===quickId)&&<QuickProgressModal item={data.applications.find(item=>item.id===quickId)!} onClose={()=>setQuickId(null)} refresh={refresh}/>}
      {detailId&&data.applications.find(item=>item.id===detailId)&&<ApplicationDetailDrawer item={data.applications.find(item=>item.id===detailId)!} interviews={interviewsByApplication.get(detailId)||[]} resumeOptions={resumeOptions} onClose={()=>setDetailId(null)} refresh={refresh} go={go}/>}
      {showNew && <Modal title="新建投递" subtitle="默认记录为“已投递”，日期使用今天；之后都可以调整。" onClose={() => setShowNew(false)} wide><ApplicationForm onSubmit={create} onClose={() => setShowNew(false)} busy={busy} resumeOptions={resumeOptions} /></Modal>}
    </>
  );
}

function ApplicationRow({ item, interviews, selected, onSelect, onQuick, onDetails }: { item: Application; interviews:Interview[]; selected:boolean; onSelect:()=>void; onQuick:()=>void; onDetails:()=>void }) {
  const currentInterview=preferredInterview(interviews);
  return <tr id={`application-${item.id}`} className={`${terminalStatuses.has(item.currentStatus) ? "terminal-row" : ""} status-row-${item.currentStatus.replace(/\s/g,'-')}`}>
    <td className="check-column"><input type="checkbox" checked={selected} onChange={onSelect} aria-label={`选择 ${item.companyName} ${item.positionName}`}/></td>
    <td><div className="entity-cell"><span className="company-avatar">{item.companyName.slice(0, 1)}</span><span><strong>{item.companyName}</strong><small>{item.positionName}{item.city ? ` · ${item.city}` : ""}</small></span></div></td>
    <td><button type="button" className="quick-stage-trigger" onClick={onQuick} title="快速更新当前环节"><span className="application-stage-cell"><StatusBadge value={item.currentStatus}/>{currentInterview&&<small>{interviewProgressLabel(currentInterview)}</small>}</span><Zap size={13}/></button></td>
    <td><button type="button" className="stage-state-trigger" onClick={onQuick} title="快速更新环节状态">{stageStateLabel(item.stageState)}</button></td>
    <td><button type="button" className={`stage-time-cell tone-${stageTimeTone(item)}`} onClick={onQuick} title={item.stageTimeNote||"设置环节时间"}><CalendarClock size={14}/><span><strong>{stageTimeRelative(item)|| (item.stageState==="已安排"?"待补充时间":"—")}</strong>{item.stageCompletedAt&&item.stageScheduledAt&&<small>原计划 {stageTimeLabel(item)}</small>}</span></button></td>
    <td>{item.appliedAt || "—"}</td><td>{formatDateTime(item.statusUpdateTime)}</td><td><Priority value={item.priority}/></td>
    <td><div className="row-actions">{item.jobLink&&<a className="icon-button" href={item.jobLink} target="_blank" rel="noreferrer" title="打开岗位链接" aria-label="打开岗位链接"><Link2 size={14}/></a>}{item.resumePath&&<a className="icon-button" href={`/resume/${item.id}`} target="_blank" rel="noreferrer" title="直接打开简历" aria-label="直接打开简历"><FileText size={14}/></a>}<button className="row-toggle" onClick={onDetails}>查看详情</button></div></td>
  </tr>;
}

function QuickProgressModal({item,onClose,refresh}:{item:Application;onClose:()=>void;refresh:()=>Promise<void>}){
  const [busy, setBusy] = useState(false);
  const [currentStatus,setCurrentStatus]=useState(item.currentStatus);
  const [stageState,setStageState]=useState(item.stageState);
  const [timeType,setTimeType]=useState<"deadline"|"appointment">(item.stageTimeType||"deadline");
  const [scheduledAt,setScheduledAt]=useState(item.stageScheduledAt);
  const [completedAt,setCompletedAt]=useState(item.stageCompletedAt);
  const [timeNote,setTimeNote]=useState(item.stageTimeNote);
  const [dateOnly,setDateOnly]=useState(/^\d{4}-\d{2}-\d{2}$/.test(item.stageScheduledAt));
  const showSchedule=stageState==="已安排"||Boolean(scheduledAt)||Boolean(completedAt);
  function changeStatus(value:string){setCurrentStatus(value);if(value!==item.currentStatus){setScheduledAt("");setCompletedAt("");setTimeNote("");setDateOnly(false)}}
  function toggleDateOnly(checked:boolean){setDateOnly(checked);setScheduledAt(value=>checked?value.slice(0,10):value?`${value.slice(0,10)}T09:00`:"")}
  async function update(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);const values=Object.fromEntries(new FormData(event.currentTarget));
    const payload={
      currentStatus,stageState,nextAction:item.nextAction,
      city:item.city,source:item.source,jobLink:item.jobLink,category:item.category,tags:item.tags,jdText:item.jdText,
      priority:item.priority,appliedAt:item.appliedAt,applicationDeadline:item.applicationDeadline,
      nextActionDueAt:item.nextActionDueAt,lastFollowUpAt:item.lastFollowUpAt,stageTimeType:showSchedule?timeType:"",
      stageScheduledAt:showSchedule?String(values.stageScheduledAt||""):"",stageCompletedAt:showSchedule?completedAt:"",stageTimeNote:showSchedule?String(values.stageTimeNote||""):"",
    };
    try{await api(`/applications/${item.id}`,{method:"PATCH",...jsonBody(payload)});await refresh();onClose();}
    catch(reason){window.alert(reason instanceof Error?reason.message:"环节更新失败");setBusy(false);}
  }
  return <Modal title="快速更新进度" subtitle={`${item.companyName} · ${item.positionName}`} onClose={onClose}><form onSubmit={update} className="quick-progress-form">
    <Field label="当前环节"><select name="currentStatus" value={currentStatus} autoFocus onChange={event=>changeStatus(event.target.value)}>{(statuses.includes(item.currentStatus)?statuses:[item.currentStatus,...statuses]).map(value=><option key={value}>{value}</option>)}</select></Field>
    <Field label="这一步现在怎样了？" hint="只描述当前一步；进入下一环节时再修改上方选项。"><select name="stageState" value={stageState} onChange={event=>setStageState(event.target.value)}>{stageStateChoices(item.stageState).map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></Field>
    <div className="stage-state-help"><span><b>待我处理</b>还有测评、材料或准备工作没做</span><span><b>已安排时间</b>已经收到具体时间，尚未进行</span><span><b>等待公司结果</b>我方已完成，等待推进或通知</span></div>
    {showSchedule&&<div className="stage-schedule-editor"><div className="stage-time-type" role="group" aria-label="时间性质"><button type="button" className={timeType==="deadline"?"active":""} onClick={()=>setTimeType("deadline")}><strong>截止时间</strong><small>在此之前完成</small></button><button type="button" className={timeType==="appointment"?"active":""} onClick={()=>setTimeType("appointment")}><strong>固定时间</strong><small>在此时间参加</small></button></div><div className="stage-time-input-row"><Field label={timeType==="deadline"?"最晚完成时间":"参加时间"}><input name="stageScheduledAt" type={dateOnly?"date":"datetime-local"} value={scheduledAt} required={stageState==="已安排"} onChange={event=>setScheduledAt(event.target.value)}/></Field><label className="date-only-toggle"><input type="checkbox" checked={dateOnly} onChange={event=>toggleDateOnly(event.target.checked)}/><span>通知中只有日期</span></label></div><Field label="时间备注" hint="可记录邮件有效期、会议入口或提前准备事项。"><input name="stageTimeNote" value={timeNote} onChange={event=>setTimeNote(event.target.value)} placeholder="例如：链接当天 23:59 失效"/></Field>{completedAt&&<p className="stage-completed-note"><CheckSquare2 size={14}/>{completedTimeLabel(completedAt)}</p>}</div>}
    <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy}>{busy?"保存中…":"保存进度"}</button></div>
  </form></Modal>;
}

function StageScheduleFields({item}:{item:Application}){
  const [dateOnly,setDateOnly]=useState(/^\d{4}-\d{2}-\d{2}$/.test(item.stageScheduledAt));
  const [scheduledAt,setScheduledAt]=useState(item.stageScheduledAt);
  function toggle(checked:boolean){setDateOnly(checked);setScheduledAt(value=>checked?value.slice(0,10):value?`${value.slice(0,10)}T09:00`:"")}
  return <section className="drawer-schedule-section"><header><div><span>环节时间</span><strong>{item.stageScheduledAt?stageTimeLabel(item):"尚未安排"}</strong></div><label className="date-only-toggle"><input type="checkbox" checked={dateOnly} onChange={event=>toggle(event.target.checked)}/><span>通知中只有日期</span></label></header><div className="editor-grid">
    <Field label="时间性质"><select name="stageTimeType" defaultValue={item.stageTimeType}><option value="">暂不设置</option><option value="deadline">截止时间 · 在此之前完成</option><option value="appointment">固定时间 · 在此时间参加</option></select></Field>
    <Field label="计划时间"><input name="stageScheduledAt" type={dateOnly?"date":"datetime-local"} value={scheduledAt} onChange={event=>setScheduledAt(event.target.value)}/></Field>
    <Field label="实际完成时间"><input name="stageCompletedAt" type="datetime-local" defaultValue={dateTimeInputValue(item.stageCompletedAt)}/></Field>
    <Field label="时间备注"><input name="stageTimeNote" defaultValue={item.stageTimeNote} placeholder="例如：链接当天失效"/></Field>
  </div></section>;
}

function dateTimeInputValue(value:string){
  if(!value||/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))return value;
  const date=new Date(value);if(Number.isNaN(date.getTime()))return value.slice(0,16);
  return new Date(date.getTime()-date.getTimezoneOffset()*60_000).toISOString().slice(0,16);
}

function ApplicationDetailDrawer({ item, interviews, resumeOptions, onClose, refresh, go }: { item: Application; interviews:Interview[]; resumeOptions:ResumeOption[]; onClose:()=>void; refresh: () => Promise<void>; go: (page: string) => void }) {
  const [busy, setBusy] = useState(false);
  const currentInterview=preferredInterview(interviews);
  const timeline=[...item.statusHistory.map((event,index)=>({key:`status-${event.time}-${index}`,time:event.time,title:event.from?`${event.from} → ${event.to}`:event.to,detail:event.note||"投递状态更新",kind:"status"})),...interviews.map(interview=>({key:`interview-${interview.id}`,time:interview.interviewTime||interview.createdAt,title:`面试记录 · ${interview.round}`,detail:[interviewResultLabel(interview.result),interview.interviewMode].filter(Boolean).join(" · "),kind:"interview"}))].sort((a,b)=>new Date(b.time).getTime()-new Date(a.time).getTime());
  async function update(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = new FormData(event.currentTarget);
    const file = values.get("resumeFile");
    const existingResumeApplicationID = Number(values.get("existingResumeApplicationId") || 0);
    values.delete("resumeFile"); values.delete("existingResumeApplicationId");
    const payload = Object.fromEntries(values.entries()); payload.priority = Number(payload.priority) as never;
    try {
      await api(`/applications/${item.id}`, { method: "PATCH", ...jsonBody(payload) });
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "投递更新失败");
      setBusy(false);
      return;
    }
    if (existingResumeApplicationID > 0) {
      try {
        await linkExistingResume(item.id, existingResumeApplicationID);
      } catch (reason) {
        window.alert(`投递信息已保存，但已有简历关联失败：${reason instanceof Error ? reason.message : "请稍后重试"}`);
      }
    } else if (file instanceof File && file.size) {
      try {
        await uploadResume(item.id, file);
      } catch (reason) {
        window.alert(`投递信息已保存，但简历绑定失败：${reason instanceof Error ? reason.message : "请稍后重试"}`);
      }
    }
    await refresh();
    setBusy(false);
  }
  return <Drawer title={`${item.companyName} · ${item.positionName}`} subtitle="完整资料、简历关联与流转记录" onClose={onClose}><form className="application-drawer-form" onSubmit={update}>
        <div className="editor-summary"><div><span className="eyebrow">APPLICATION #{item.id}</span><h3>{item.companyName} · {item.positionName}</h3><p>{item.jdText ? item.jdText.slice(0, 180) : "尚未保存 JD，建议在岗位关闭前补充。"}</p></div><div className="editor-quick-actions"><button type="button" className="secondary-button" onClick={() => go(`ai?application=${item.id}`)}><Sparkles size={15} />岗位准备</button>{item.jobLink && <a className="secondary-button" href={item.jobLink} target="_blank" rel="noreferrer">岗位链接 <ExternalLink size={14} /></a>}{item.resumePath && <a className="secondary-button" href={`/resume/${item.id}`} target="_blank" rel="noreferrer">查看简历 <ExternalLink size={14} /></a>}</div></div>
        <div className="editor-grid">
          <Field label="当前环节"><select name="currentStatus" defaultValue={item.currentStatus}>{(statuses.includes(item.currentStatus) ? statuses : [item.currentStatus, ...statuses]).map((value) => <option key={value}>{value}</option>)}</select></Field>
          <Field label="环节状态"><select name="stageState" defaultValue={item.stageState}>{stageStateChoices(item.stageState).map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></Field>
          <Field label="优先级"><select name="priority" defaultValue={item.priority}>{[0, 1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value ? `${value} 级` : "普通"}</option>)}</select></Field>
          <Field label="城市"><input name="city" defaultValue={item.city} /></Field>
          <Field label="投递来源"><input name="source" defaultValue={item.source} list="sources" /></Field>
          <Field label="岗位类型"><input name="category" defaultValue={item.category} list="categories" /></Field>
          <Field label="自定义标签"><input name="tags" defaultValue={item.tags} placeholder="供应链, 新能源, 管培" /></Field>
          <Field label="岗位链接" span><input name="jobLink" type="url" defaultValue={item.jobLink} /></Field>
          <Field label="投递日期"><input name="appliedAt" type="date" defaultValue={item.appliedAt} /></Field>
          <ResumeBindingField currentPath={item.resumePath} options={resumeOptions.filter(option=>option.applicationId!==item.id&&option.path.toLowerCase()!==item.resumePath.toLowerCase())}/>
          <Field label="JD 原文" hint="岗位关闭后仍保留，岗位准备助手也会以此为依据。" span><textarea name="jdText" rows={7} defaultValue={item.jdText} /></Field>
          <input type="hidden" name="applicationDeadline" value={item.applicationDeadline} /><input type="hidden" name="nextActionDueAt" value={item.nextActionDueAt} /><input type="hidden" name="lastFollowUpAt" value={item.lastFollowUpAt} />
        </div>
        <StageScheduleFields item={item}/>
        <details className="optional-records"><summary>补充记录（可选）</summary><Field label="下一步行动" hint="多数情况下环节已经说明下一步；只有需要额外提醒时再填写。"><input name="nextAction" defaultValue={item.nextAction} list="next-actions" placeholder="例如：周五前联系 HR" /></Field></details>
        {currentInterview&&<div className="application-interview-context"><div><span>当前面试进展</span><strong>{currentInterview.round} · {interviewResultLabel(currentInterview.result)}</strong><small><CalendarClock size={13}/>{currentInterview.interviewTime?formatDateTime(currentInterview.interviewTime):"时间待补充"}{currentInterview.interviewMode&&<><i>·</i><Video size={13}/>{currentInterview.interviewMode}</>}</small></div><button type="button" className="secondary-button" onClick={()=>go(`interviews?interview=${currentInterview.id}`)}>查看安排与复盘</button></div>}
        <div className="history-block"><h4>流转详情</h4>{timeline.length ? <ol>{timeline.map((event) => <li key={event.key} className={event.kind==="interview"?"interview-event":""}><span /><div><strong>{event.title}</strong><small>{formatDateTime(event.time)} · {event.detail}</small></div></li>)}</ol> : <p className="muted-text">暂无流转记录</p>}</div>
        <div className="editor-actions"><ConfirmButton confirmText={`确定删除 ${item.companyName} · ${item.positionName}？数据库记录会删除，绑定文件仍保留。`} onConfirm={async () => { await api(`/applications/${item.id}`, { method: "DELETE" }); onClose(); await refresh(); }}><Trash2 size={15} />删除投递</ConfirmButton><button className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存修改"}</button></div>
      </form></Drawer>;
}

function ApplicationForm({ onSubmit, onClose, busy, resumeOptions }: { onSubmit: (event: React.FormEvent<HTMLFormElement>) => void; onClose: () => void; busy: boolean; resumeOptions:ResumeOption[] }) {
  return <form className="application-create-form" onSubmit={onSubmit}><div className="application-create-layout">
    <section className="application-form-section application-role-section"><header><span><Building2 size={18}/></span><div><h3>岗位信息</h3><p>先保存最重要的公司、岗位、链接和 JD。</p></div></header><div className="application-form-grid">
      <Field label="公司名称"><input name="companyName" required autoFocus placeholder="例如：华为" /></Field>
      <Field label="岗位名称"><input name="positionName" required placeholder="例如：硬件技术工程师" /></Field>
      <Field label="岗位链接" span><input name="jobLink" type="url" placeholder="https://careers.example.com/job/..." /></Field>
      <Field label="JD 原文" hint="建议完整保存；岗位关闭后仍可复盘，也可供岗位准备助手使用。" span><textarea name="jdText" rows={10} placeholder="粘贴岗位职责、任职要求和加分项…" /></Field>
    </div></section>
    <aside className="application-form-aside">
      <section className="application-form-section"><header><span><Workflow size={18}/></span><div><h3>投递状态</h3><p>默认按今天已投递记录，之后可随时调整。</p></div></header><div className="application-form-grid">
        <Field label="当前环节"><select name="currentStatus" defaultValue="已投递">{statuses.map((value) => <option key={value}>{value}</option>)}</select></Field>
        <Field label="环节状态"><select name="stageState" defaultValue="已完成，等待结果">{stageStateChoices("已完成，等待结果").map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></Field>
        <Field label="投递日期"><input name="appliedAt" type="date" defaultValue={todayISO()} /></Field>
        <Field label="优先级"><select name="priority" defaultValue="0">{[0, 1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value ? `${value} 级` : "普通"}</option>)}</select></Field>
      </div></section>
      <section className="application-form-section"><header><span><FolderArchive size={18}/></span><div><h3>分类与材料</h3><p>用于后续筛选和快速找到当时使用的简历。</p></div></header><div className="application-form-grid">
        <Field label="城市"><input name="city" placeholder="例如：上海" /></Field>
        <Field label="投递来源"><input name="source" list="sources" placeholder="官网 / 内推" /></Field>
        <Field label="岗位类型"><input name="category" list="categories" placeholder="研发 / 供应链 / 产品" /></Field>
        <Field label="自定义标签"><input name="tags" placeholder="新能源, 管培" /></Field>
        <ResumeBindingField options={resumeOptions}/>
      </div></section>
    </aside>
    <input type="hidden" name="nextAction" value="" /><input type="hidden" name="applicationDeadline" value="" /><input type="hidden" name="nextActionDueAt" value="" /><input type="hidden" name="lastFollowUpAt" value="" />
  </div><div className="modal-actions application-create-actions"><span>带 * 的公司与岗位为必填项</span><button type="button" className="secondary-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy}>{busy ? "保存中…" : "保存投递"}</button></div>
  <datalist id="sources">{sources.map((value) => <option key={value} value={value} />)}</datalist><datalist id="categories">{categories.map((value) => <option key={value} value={value} />)}</datalist><datalist id="next-actions">{["等待结果", "完成测评", "准备笔试", "准备业务面", "准备 HR 面", "跟进进度", "接受 Offer"].map((value) => <option key={value} value={value} />)}</datalist></form>;
}

async function uploadResume(id: number, file: File) {
  const body = new FormData(); body.append("resume", file);
  await api(`/applications/${id}/resume`, { method: "POST", body });
}

async function linkExistingResume(id:number,sourceApplicationId:number){
  await api(`/applications/${id}/resume/link`,{method:"POST",...jsonBody({sourceApplicationId})});
}

function existingResumeOptions(applications:Application[]):ResumeOption[]{
  const seen=new Set<string>();
  const options:ResumeOption[]=[];
  applications.forEach(item=>{
    const path=item.resumePath.trim();
    const key=path.toLowerCase();
    if(!path||seen.has(key))return;
    seen.add(key);
    const name=path.split(/[\\/]/).pop()||"已有简历";
    options.push({applicationId:item.id,path,label:`${name} · ${item.companyName} / ${item.positionName}`});
  });
  return options;
}

function ResumeBindingField({options,currentPath=""}:{options:ResumeOption[];currentPath?:string}){
  const [mode,setMode]=useState<"keep"|"reuse"|"upload">(currentPath?"keep":"upload");
  return <div className="field field-span resume-binding-field"><span>简历关联</span><div className="resume-binding-mode" role="group" aria-label="简历关联方式">
    {currentPath&&<button type="button" className={mode==="keep"?"active":""} onClick={()=>setMode("keep")}>保持当前</button>}
    <button type="button" className={mode==="reuse"?"active":""} disabled={!options.length} onClick={()=>setMode("reuse")}>复用已有</button>
    <button type="button" className={mode==="upload"?"active":""} onClick={()=>setMode("upload")}>上传新文件</button>
  </div>{mode==="reuse"?<select name="existingResumeApplicationId" defaultValue=""><option value="">暂不绑定</option>{options.map(option=><option key={option.path} value={option.applicationId}>{option.label}</option>)}</select>:mode==="upload"?<input name="resumeFile" type="file" accept=".pdf,.doc,.docx"/>:<div className="resume-binding-current">继续使用当前已绑定的简历文件</div>}<small>{mode==="reuse"?"只建立关联，不会复制文件；一份简历可以用于多个投递。":mode==="upload"?"支持 PDF、DOC、DOCX，最大 25 MB；也可以留空稍后绑定。":"保存岗位信息时不会改动当前简历。"}</small></div>;
}

function exportApplicationsCSV(items:Application[]){
  const rows=[["公司","岗位","类型","城市","投递来源","当前环节","环节状态","时间性质","环节时间","实际完成时间","时间备注","投递日期","状态更新时间"],...items.map(item=>[item.companyName,item.positionName,item.category,item.city,item.source,item.currentStatus,item.stageState,item.stageTimeType==="deadline"?"截止时间":item.stageTimeType==="appointment"?"固定时间":"",item.stageScheduledAt,item.stageCompletedAt,item.stageTimeNote,item.appliedAt,item.statusUpdateTime])];
  const csv="\uFEFF"+rows.map(row=>row.map(value=>`"${String(value||"").replace(/"/g,'""')}"`).join(",")).join("\r\n");downloadBlob(new Blob([csv],{type:"text/csv;charset=utf-8"}),`投递记录-${todayISO()}.csv`);
}
async function exportApplicationsImage(items:Application[]){
  const width=1200,rowHeight=66,height=170+Math.min(items.length,20)*rowHeight;const canvas=document.createElement("canvas");canvas.width=width;canvas.height=height;const ctx=canvas.getContext("2d");if(!ctx)return;
  ctx.fillStyle="#f5f7fb";ctx.fillRect(0,0,width,height);ctx.fillStyle="#111827";ctx.font="700 34px 'Microsoft YaHei',sans-serif";ctx.fillText("求职投递进度",56,62);ctx.fillStyle="#64748b";ctx.font="16px 'Microsoft YaHei',sans-serif";ctx.fillText(`${todayISO()} · 共 ${items.length} 条（仅展示前 20 条）`,56,96);
  items.slice(0,20).forEach((item,index)=>{const y=126+index*rowHeight;ctx.fillStyle="#ffffff";ctx.fillRect(40,y,width-80,rowHeight-8);ctx.fillStyle="#182230";ctx.font="700 18px 'Microsoft YaHei',sans-serif";ctx.fillText(item.companyName,60,y+27);ctx.fillStyle="#667085";ctx.font="14px 'Microsoft YaHei',sans-serif";ctx.fillText(item.positionName,260,y+27);ctx.fillStyle="#4f46e5";ctx.fillText(item.currentStatus,700,y+27);ctx.fillStyle="#667085";ctx.fillText(item.category||"未分类",855,y+27);ctx.fillText(item.appliedAt||"—",1000,y+27)});
  const blob=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,"image/png"));if(blob)downloadBlob(blob,`投递进度分享图-${todayISO()}.png`);
}
function downloadBlob(blob:Blob,name:string){const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
