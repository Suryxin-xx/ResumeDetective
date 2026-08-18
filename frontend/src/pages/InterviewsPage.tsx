import { useState } from "react";
import { MessageSquarePlus, Pencil, Search, Trash2 } from "lucide-react";
import { api, formatDateTime, jsonBody } from "../api";
import { ConfirmButton, EmptyState, Field, PageHeader, Panel, StatusBadge } from "../components";
import type { PageProps } from "../App";
import type { Interview } from "../types";

const rounds = ["AI 面试", "一面", "二面", "三面", "HR 面", "其他"];
const results = [
  { value: "待确认", label: "结果待通知（尚未收到官方结果）" },
  { value: "通过", label: "通过" },
  { value: "未通过", label: "未通过" },
];

function resultLabel(result: string) {
  return result === "待确认" ? "结果待通知" : result || "结果待通知";
}

export default function InterviewsPage({ data, refresh }: PageProps) {
  const [editor, setEditor] = useState<Interview | "new" | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [query,setQuery]=useState("");
  const [resultFilter,setResultFilter]=useState("全部结果");
  const matches=(item:Interview)=>(!query||`${item.companyName} ${item.positionName} ${item.round} ${item.questions} ${item.weakPoints}`.toLowerCase().includes(query.toLowerCase()))&&(resultFilter==="全部结果"||item.result===resultFilter);
  const active = data.interviews.filter((item) => item.result !== "未通过"&&matches(item));
  const history = data.interviews.filter((item) => item.result === "未通过"&&matches(item));
  const editing = editor !== null && editor !== "new" ? editor : null;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    payload.applicationId = Number(payload.applicationId) as never;
    try {
      await api(editing ? `/interviews/${editing.id}` : "/interviews", {
        method: editing ? "PATCH" : "POST",
        ...jsonBody(payload),
      });
      setEditor(null);
      await refresh();
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  return <>
    <PageHeader title="面试复盘" description="按时间线记录问题、薄弱点与后续行动；收到结果后可随时编辑。" action={<button className="primary-button" onClick={() => setEditor("new")}><MessageSquarePlus size={17} />记录面试</button>} />
    <Panel className="filter-panel"><div className="filter-row"><label className="search-box"><Search size={16}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索公司、岗位或面试问题"/></label><select className="compact-select" value={resultFilter} onChange={event=>setResultFilter(event.target.value)}><option>全部结果</option><option value="待确认">结果待通知</option><option>通过</option><option>未通过</option></select><span className="result-count">{active.length+history.length} 条复盘</span></div></Panel>
    {editor !== null && <Panel title={editing ? "编辑面试复盘" : "新增面试复盘"} description={editing ? "修改后会同步到 Excel 镜像。" : "“结果待通知”表示面试已结束，但暂未收到官方结果。"}>
      <form key={editing?.id ?? "new"} className="interview-form" onSubmit={save}>
        <Field label="对应岗位"><select name="applicationId" required defaultValue={editing?.applicationId ?? ""}><option value="" disabled>选择投递岗位</option>{data.applications.map((item) => <option key={item.id} value={item.id}>{item.companyName} · {item.positionName}{item.currentStatus === "终止" ? "（已终止）" : ""}</option>)}</select></Field>
        <Field label="轮次"><select name="round" defaultValue={editing?.round || "一面"}>{rounds.map((value) => <option key={value}>{value}</option>)}</select></Field>
        <Field label="面试时间"><input name="interviewTime" type="datetime-local" defaultValue={toDateTimeLocal(editing?.interviewTime)} /></Field>
        <Field label="结果" hint="结果待通知：面试完成，尚未收到官方通知。"><select name="result" defaultValue={editing?.result || "待确认"}>{results.map((result) => <option key={result.value} value={result.value}>{result.label}</option>)}</select></Field>
        <Field label="整体总结" span><textarea name="summary" rows={3} defaultValue={editing?.summary ?? ""} /></Field>
        <Field label="主要问题" span><textarea name="questions" rows={5} defaultValue={editing?.questions ?? ""} /></Field>
        <Field label="薄弱点"><textarea name="weakPoints" rows={4} defaultValue={editing?.weakPoints ?? ""} /></Field>
        <Field label="后续行动"><textarea name="followUp" rows={4} defaultValue={editing?.followUp ?? ""} /></Field>
        <div className="form-actions field-span"><button type="button" className="secondary-button" onClick={() => setEditor(null)}>取消</button><button className="primary-button">{editing ? "保存修改" : "保存复盘"}</button></div>
      </form>
    </Panel>}
    <Panel title="近期复盘" description="“结果待通知”和“通过”的记录保留在这里；未通过记录归入历史区。">{active.length ? <div className="interview-cards interview-timeline">{active.map((item) => <InterviewCard key={item.id} item={item} refresh={refresh} onEdit={() => setEditor(item)} />)}</div> : <EmptyState title="还没有符合条件的复盘" description="完成一次面试后，把问题和薄弱点留在这里。" />}</Panel>
    <Panel title="历史复盘" action={<button className="text-button" onClick={() => setShowHistory((value) => !value)}>{showHistory ? "收起" : `展开 ${history.length} 条`}</button>}>{showHistory && (history.length ? <div className="interview-cards muted-cards">{history.map((item) => <InterviewCard key={item.id} item={item} refresh={refresh} onEdit={() => setEditor(item)} />)}</div> : <EmptyState title="没有未通过复盘" description="面试结果标为“未通过”的记录会自动归入这里。" />)}</Panel>
  </>;
}

function InterviewCard({ item, refresh, onEdit }: { item: Interview; refresh: () => Promise<void>; onEdit: () => void }) {
  return <article><div className="interview-card-head"><div><span>{item.round}</span><h3>{item.companyName} · {item.positionName}</h3><small>{formatDateTime(item.interviewTime || item.createdAt)}</small></div><StatusBadge value={resultLabel(item.result)} /></div>{item.summary && <p className="interview-summary">{item.summary}</p>}<div className="interview-details">{item.questions && <section><h4>主要问题</h4><p>{item.questions}</p></section>}{item.weakPoints && <section><h4>薄弱点</h4><p>{item.weakPoints}</p></section>}{item.followUp && <section><h4>后续行动</h4><p>{item.followUp}</p></section>}</div><div className="interview-actions"><button type="button" className="text-button" onClick={onEdit}><Pencil size={14} />编辑</button><ConfirmButton className="text-button danger-text" confirmText="删除这条面试复盘？" onConfirm={async () => { await api(`/interviews/${item.id}`, { method: "DELETE" }); await refresh(); }}><Trash2 size={14} />删除</ConfirmButton></div></article>;
}

function toDateTimeLocal(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
