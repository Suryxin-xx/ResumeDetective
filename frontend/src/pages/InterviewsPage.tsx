import { useEffect, useState } from "react";
import { CalendarClock, ExternalLink, MessageSquarePlus, Pencil, Search, Trash2, Video } from "lucide-react";
import { api, formatDateTime, jsonBody } from "../api";
import { ConfirmButton, EmptyState, Field, PageHeader, Panel, StatusBadge } from "../components";
import { interviewResultLabel, interviewStage, interviewStageState } from "../interviewProgress";
import type { PageProps } from "../App";
import type { Interview } from "../types";

const rounds = ["AI 面试", "一面", "二面", "三面", "HR 面", "其他"];
const interviewModes = ["视频面试", "电话面试", "现场面试", "其他"];
const terminalStatuses = new Set(["终止", "已终止", "未通过", "主动放弃", "流程结束"]);
const results = [
  { value: "待面试", label: "待面试（已安排，尚未进行）" },
  { value: "待确认", label: "结果待通知（尚未收到官方结果）" },
  { value: "通过", label: "通过" },
  { value: "未通过", label: "未通过" },
];

function routeSelection() {
  const query = window.location.hash.split("?")[1] || "";
  const params = new URLSearchParams(query);
  return { applicationId: Number(params.get("application")) || 0, interviewId: Number(params.get("interview")) || 0, hasQuery: Boolean(query) };
}

export default function InterviewsPage({ data, refresh }: PageProps) {
  const [selection] = useState(routeSelection);
  const [presetApplicationId, setPresetApplicationId] = useState(selection.applicationId);
  const [editor, setEditor] = useState<Interview | "new" | null>(() => data.interviews.find((item) => item.id === selection.interviewId) || (selection.applicationId ? "new" : null));
  const [showHistory, setShowHistory] = useState(false);
  const [query,setQuery]=useState("");
  const [resultFilter,setResultFilter]=useState("全部结果");
  const matches=(item:Interview)=>(!query||`${item.companyName} ${item.positionName} ${item.round} ${item.interviewMode} ${item.scheduleNotes} ${item.questions} ${item.weakPoints}`.toLowerCase().includes(query.toLowerCase()))&&(resultFilter==="全部结果"||item.result===resultFilter);
  const active = data.interviews.filter((item) => item.result !== "未通过"&&matches(item));
  const history = data.interviews.filter((item) => item.result === "未通过"&&matches(item));
  const activeApplications = data.applications.filter((item) => !terminalStatuses.has(item.currentStatus));
  const historicalApplications = data.applications.filter((item) => terminalStatuses.has(item.currentStatus));
  const editing = editor !== null && editor !== "new" ? editor : null;
  useEffect(() => {
    if (selection.hasQuery) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/interviews`);
  }, [selection.hasQuery]);

  function openNew(applicationId = 0) {
    setPresetApplicationId(applicationId);
    setEditor("new");
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const syncApplicationStage = values.get("syncApplicationStage") === "on";
    values.delete("syncApplicationStage");
    const payload = Object.fromEntries(values);
    payload.applicationId = Number(payload.applicationId) as never;
    let syncWarning = "";
    try {
      await api(editing ? `/interviews/${editing.id}` : "/interviews", {
        method: editing ? "PATCH" : "POST",
        ...jsonBody(payload),
      });
      if (syncApplicationStage) {
        try {
          await api(`/applications/${payload.applicationId}/interview-stage`, {
            method: "POST",
            ...jsonBody({ round: payload.round, result: payload.result }),
          });
        } catch (reason) {
          syncWarning = reason instanceof Error ? reason.message : "投递状态同步失败";
        }
      }
      setEditor(null);
      setPresetApplicationId(0);
      await refresh();
      if (syncWarning) window.alert(`面试记录已保存，但${syncWarning}`);
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  return <>
    <PageHeader title="面试安排与复盘" description="先保存时间、形式和会议链接，结束后再补充问题、结果与后续行动。" action={<button className="primary-button" onClick={() => openNew()}><MessageSquarePlus size={17} />记录面试</button>} />
    <Panel className="filter-panel"><div className="filter-row"><label className="search-box"><Search size={16}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索公司、岗位、安排或面试问题"/></label><select className="compact-select" value={resultFilter} onChange={event=>setResultFilter(event.target.value)}><option>全部结果</option><option>待面试</option><option value="待确认">结果待通知</option><option>通过</option><option>未通过</option></select><span className="result-count">{active.length+history.length} 条记录</span></div></Panel>
    {editor !== null && <Panel title={editing ? "编辑面试安排与复盘" : "新增面试安排"} description={editing ? "安排信息会同步显示在首页重点面试区域。" : "收到邮件后先保存时间和会议链接，面试结束再回来补充复盘。"}>
      <form key={editing?.id ?? "new"} className="interview-form" onSubmit={save}>
        <Field label="对应岗位"><select name="applicationId" required defaultValue={editing?.applicationId || presetApplicationId || ""}><option value="" disabled>选择投递岗位</option><optgroup label="进行中的岗位">{activeApplications.map((item) => <option key={item.id} value={item.id}>{item.companyName} · {item.positionName}（{item.currentStatus}）</option>)}</optgroup>{historicalApplications.length > 0 && <optgroup label="已终止岗位（历史复盘）">{historicalApplications.map((item) => <option key={item.id} value={item.id}>{item.companyName} · {item.positionName}</option>)}</optgroup>}</select></Field>
        <Field label="轮次"><select name="round" defaultValue={editing?.round || "一面"}>{rounds.map((value) => <option key={value}>{value}</option>)}</select></Field>
        <Field label="面试时间"><input name="interviewTime" type="datetime-local" defaultValue={toDateTimeLocal(editing?.interviewTime)} /></Field>
        <Field label="面试形式"><select name="interviewMode" defaultValue={editing?.interviewMode || "视频面试"}>{interviewModes.map((value) => <option key={value}>{value}</option>)}</select></Field>
        <Field label="会议链接" hint="仅支持 http/https；保存后可从首页直接打开。" span><input name="meetingLink" type="url" placeholder="https://..." defaultValue={editing?.meetingLink ?? ""} /></Field>
        <Field label="安排备注" hint="例如：提前 10 分钟入会、准备身份证、面试官部门。" span><textarea name="scheduleNotes" rows={3} defaultValue={editing?.scheduleNotes ?? ""} /></Field>
        <Field label="结果" hint="面试完成后，再从“待面试”改为结果待通知或最终结果。"><select name="result" defaultValue={editing?.result || "待面试"}>{results.map((result) => <option key={result.value} value={result.value}>{result.label}</option>)}</select></Field>
        <label className="interview-sync-option field-span"><input type="checkbox" name="syncApplicationStage" defaultChecked /><span><strong>同步到投递进度</strong><small>AI 面试同步为“AI 面试”；一面、二面、三面同步为“业务面试”；HR 面同步为“HR 面”。Offer 或已终止岗位不会被覆盖。</small></span></label>
        <Field label="整体总结" span><textarea name="summary" rows={3} defaultValue={editing?.summary ?? ""} /></Field>
        <Field label="主要问题" span><textarea name="questions" rows={5} defaultValue={editing?.questions ?? ""} /></Field>
        <Field label="薄弱点"><textarea name="weakPoints" rows={4} defaultValue={editing?.weakPoints ?? ""} /></Field>
        <Field label="后续行动"><textarea name="followUp" rows={4} defaultValue={editing?.followUp ?? ""} /></Field>
        <div className="form-actions field-span"><button type="button" className="secondary-button" onClick={() => { setEditor(null); setPresetApplicationId(0); }}>取消</button><button className="primary-button">{editing ? "保存修改" : "保存安排"}</button></div>
      </form>
    </Panel>}
    <Panel title="近期安排与复盘" description="待面试、结果待通知和通过的记录保留在这里；未通过记录归入历史区。">{active.length ? <div className="interview-cards interview-timeline">{active.map((item) => <InterviewCard key={item.id} item={item} refresh={refresh} onEdit={() => setEditor(item)} />)}</div> : <EmptyState title="还没有符合条件的面试记录" description="收到面试通知后，先保存安排；面试结束后再补充问题和薄弱点。" />}</Panel>
    <Panel title="历史复盘" action={<button className="text-button" onClick={() => setShowHistory((value) => !value)}>{showHistory ? "收起" : `展开 ${history.length} 条`}</button>}>{showHistory && (history.length ? <div className="interview-cards muted-cards">{history.map((item) => <InterviewCard key={item.id} item={item} refresh={refresh} onEdit={() => setEditor(item)} />)}</div> : <EmptyState title="没有未通过复盘" description="面试结果标为“未通过”的记录会自动归入这里。" />)}</Panel>
  </>;
}

function InterviewCard({ item, refresh, onEdit }: { item: Interview; refresh: () => Promise<void>; onEdit: () => void }) {
  return <article><div className="interview-card-head"><div><span>{item.round}</span><h3>{item.companyName} · {item.positionName}</h3><small><CalendarClock size={13}/>{item.interviewTime ? formatDateTime(item.interviewTime) : "面试时间待补充"}{item.interviewMode && <><i>·</i><Video size={13}/>{item.interviewMode}</>}</small></div><div className="interview-card-status"><small>{interviewStage(item.round)}</small><StatusBadge value={interviewResultLabel(item.result)} /></div></div>{(item.meetingLink || item.scheduleNotes) && <div className="interview-schedule-note">{item.scheduleNotes && <p>{item.scheduleNotes}</p>}{item.meetingLink && <a href={item.meetingLink} target="_blank" rel="noreferrer"><ExternalLink size={14}/>打开会议链接</a>}</div>}{item.summary && <p className="interview-summary">{item.summary}</p>}<div className="interview-details">{item.questions && <section><h4>主要问题</h4><p>{item.questions}</p></section>}{item.weakPoints && <section><h4>薄弱点</h4><p>{item.weakPoints}</p></section>}{item.followUp && <section><h4>后续行动</h4><p>{item.followUp}</p></section>}</div><div className="interview-actions"><button type="button" className="text-button" onClick={onEdit}><Pencil size={14} />编辑</button><ConfirmButton className="text-button danger-text" confirmText="删除这条面试记录？" onConfirm={async () => { await api(`/interviews/${item.id}`, { method: "DELETE" }); await refresh(); }}><Trash2 size={14} />删除</ConfirmButton></div></article>;
}

function toDateTimeLocal(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
