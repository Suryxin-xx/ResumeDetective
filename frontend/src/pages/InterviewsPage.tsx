import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CalendarClock, ExternalLink, MessageSquarePlus, Pencil, Search, Trash2, Video } from "lucide-react";
import { api, formatDateTime, jsonBody } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel, StatusBadge } from "../components";
import { interviewResultLabel, interviewStage } from "../interviewProgress";
import type { PageProps } from "../App";
import type { Interview } from "../types";
import "./interviews.css";

const rounds = ["AI 面试", "一面", "二面", "三面", "HR 面", "其他"];
const interviewModes = ["视频面试", "电话面试", "现场面试", "其他"];
const terminalStatuses = new Set(["终止", "已终止", "未通过", "主动放弃", "流程结束"]);
const activeResults = new Set(["待面试", "待确认"]);
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
  const [query, setQuery] = useState("");
  const [resultFilter, setResultFilter] = useState("全部结果");
  const [saving, setSaving] = useState(false);
  const editing = editor !== null && editor !== "new" ? editor : null;

  const normalizedQuery = query.trim().toLowerCase();
  const filteredRecords = useMemo(() => {
    return data.interviews.filter((item) => {
      const searchable = [item.companyName, item.positionName, item.round, item.interviewMode, item.scheduleNotes, item.summary, item.questions, item.weakPoints, item.followUp, interviewResultLabel(item.result)].join(" ").toLowerCase();
      return (!normalizedQuery || searchable.includes(normalizedQuery)) && (resultFilter === "全部结果" || item.result === resultFilter);
    });
  }, [data.interviews, normalizedQuery, resultFilter]);

  const active = useMemo(() => sortActive(filteredRecords.filter((item) => activeResults.has(item.result))), [filteredRecords]);
  const history = useMemo(() => sortHistory(filteredRecords.filter((item) => !activeResults.has(item.result))), [filteredRecords]);
  const activeApplications = data.applications.filter((item) => !terminalStatuses.has(item.currentStatus));
  const historicalApplications = data.applications.filter((item) => terminalStatuses.has(item.currentStatus));

  useEffect(() => {
    if (selection.hasQuery) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/interviews`);
  }, [selection.hasQuery]);

  function closeEditor() {
    if (saving) return;
    setEditor(null);
    setPresetApplicationId(0);
  }

  function openNew(applicationId = 0) {
    setPresetApplicationId(applicationId);
    setEditor("new");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;

    const values = new FormData(event.currentTarget);
    const syncApplicationStage = values.get("syncApplicationStage") === "on";
    values.delete("syncApplicationStage");
    const payload = Object.fromEntries(values) as Record<string, unknown>;
    const applicationId = Number(payload.applicationId);
    payload.applicationId = applicationId;
    let syncWarning = "";

    setSaving(true);
    try {
      await api(editing ? `/interviews/${editing.id}` : "/interviews", { method: editing ? "PATCH" : "POST", ...jsonBody(payload) });
      if (syncApplicationStage) {
        try {
          await api(`/applications/${applicationId}/interview-stage`, { method: "POST", ...jsonBody({ round: payload.round, result: payload.result }) });
        } catch (reason) {
          syncWarning = reason instanceof Error ? reason.message : "投递状态同步失败";
        }
      }
      closeEditor();
      await refresh();
      if (syncWarning) window.alert(`面试记录已保存，但${syncWarning}`);
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="interviews-page">
      <PageHeader title="面试安排与复盘" description="先保存时间、形式和会议链接，结束后再补充问题、结果与后续行动。" action={<button className="primary-button" onClick={() => openNew()}><MessageSquarePlus size={17} />记录面试</button>} />

      <Panel className="interviews-filter-panel">
        <div className="interviews-filter-row">
          <label className="interviews-search-box"><Search size={16} /><input aria-label="搜索面试记录" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司、岗位、安排或面试问题" /></label>
          <select className="compact-select interviews-result-filter" aria-label="筛选面试结果" value={resultFilter} onChange={(event) => setResultFilter(event.target.value)}><option>全部结果</option><option value="待面试">待面试</option><option value="待确认">结果待通知</option><option value="通过">通过</option><option value="未通过">未通过</option></select>
          <span className="interviews-result-count">{active.length + history.length} 条记录</span>
        </div>
      </Panel>

      <Panel title="近期安排" description="只显示待面试和结果待通知；同一状态内按面试时间排列。">
        {active.length ? <div className="interviews-list">{active.map((item) => <InterviewCard key={item.id} item={item} refresh={refresh} onEdit={() => setEditor(item)} />)}</div> : <EmptyState title="还没有符合条件的近期面试" description="收到面试通知后，先保存安排；面试结束后再补充问题和薄弱点。" />}
      </Panel>

      <Panel title="已完成复盘" description="通过和未通过的记录会自动归档到这里，避免干扰近期安排。" action={<button className="text-button interviews-history-toggle" disabled={!history.length} onClick={() => setShowHistory((value) => !value)}>{history.length ? (showHistory ? "收起" : `展开 ${history.length} 条`) : "暂无记录"}</button>}>
        {showHistory && (history.length ? <div className="interviews-list interviews-history-list">{history.map((item) => <InterviewCard key={item.id} item={item} refresh={refresh} onEdit={() => setEditor(item)} history />)}</div> : <EmptyState title="没有符合条件的历史复盘" description="调整搜索关键词或结果筛选后再试。" />)}
      </Panel>

      {editor !== null && <Modal title={editing ? "编辑面试安排与复盘" : "新增面试安排"} subtitle={editing ? "安排信息会同步显示在首页重点面试区域。" : "收到邮件后先保存时间和会议链接，面试结束再回来补充复盘。"} onClose={closeEditor} wide>
        <form key={editing?.id ?? "new"} className="interviews-modal-form" onSubmit={save}>
          <div className="modal-form-grid interviews-form-grid">
            <Field label="对应岗位"><select name="applicationId" required defaultValue={editing?.applicationId || presetApplicationId || ""}><option value="" disabled>选择投递岗位</option><optgroup label="进行中的岗位">{activeApplications.map((item) => <option key={item.id} value={item.id}>{item.companyName} · {item.positionName}（{item.currentStatus}）</option>)}</optgroup>{historicalApplications.length > 0 && <optgroup label="已终止岗位（历史复盘）">{historicalApplications.map((item) => <option key={item.id} value={item.id}>{item.companyName} · {item.positionName}</option>)}</optgroup>}</select></Field>
            <Field label="轮次"><select name="round" defaultValue={editing?.round || "一面"}>{rounds.map((value) => <option key={value}>{value}</option>)}</select></Field>
            <Field label="面试时间"><input name="interviewTime" type="datetime-local" defaultValue={toDateTimeLocal(editing?.interviewTime)} /></Field>
            <Field label="面试形式"><select name="interviewMode" defaultValue={editing?.interviewMode || "视频面试"}>{interviewModes.map((value) => <option key={value}>{value}</option>)}</select></Field>
            <Field label="会议链接" hint="仅支持 http/https；保存后可从面试卡片直接打开。" span><input name="meetingLink" type="url" placeholder="https://..." defaultValue={editing?.meetingLink ?? ""} /></Field>
            <Field label="安排备注" hint="例如：提前 10 分钟入会、准备身份证、面试官部门。" span><textarea name="scheduleNotes" rows={3} defaultValue={editing?.scheduleNotes ?? ""} /></Field>
            <Field label="结果" hint="面试完成后，再从“待面试”改为结果待通知或最终结果。"><select name="result" defaultValue={editing?.result || "待面试"}>{results.map((result) => <option key={result.value} value={result.value}>{result.label}</option>)}</select></Field>
            <label className="interview-sync-option field-span"><input type="checkbox" name="syncApplicationStage" defaultChecked /><span><strong>同步到投递进度</strong><small>AI 面试同步为“AI 面试”；一面、二面、三面同步为“业务面试”；HR 面同步为“HR 面”。Offer 或已终止岗位不会被覆盖。</small></span></label>
            <Field label="整体总结" span><textarea name="summary" rows={3} defaultValue={editing?.summary ?? ""} /></Field>
            <Field label="主要问题" span><textarea name="questions" rows={5} defaultValue={editing?.questions ?? ""} /></Field>
            <Field label="薄弱点"><textarea name="weakPoints" rows={4} defaultValue={editing?.weakPoints ?? ""} /></Field>
            <Field label="后续行动"><textarea name="followUp" rows={4} defaultValue={editing?.followUp ?? ""} /></Field>
          </div>
          <div className="modal-actions interviews-modal-actions"><button type="button" className="secondary-button" disabled={saving} onClick={closeEditor}>取消</button><button className="primary-button" disabled={saving}>{saving ? "保存中…" : editing ? "保存修改" : "保存安排"}</button></div>
        </form>
      </Modal>}
    </div>
  );
}

function InterviewCard({ item, refresh, onEdit, history = false }: { item: Interview; refresh: () => Promise<void>; onEdit: () => void; history?: boolean }) {
  const hasReview = Boolean(item.summary || item.questions || item.weakPoints || item.followUp);
  const scheduleNotes = item.scheduleNotes?.trim();

  return (
    <article className={`interview-record ${history ? "interview-record-history" : ""}`}>
      <header className="interview-record-header">
        <div className="interview-record-title">
          <span className="interview-record-round">{item.round || "未设置轮次"}</span>
          <h3 title={`${item.companyName} · ${item.positionName}`}>{item.companyName} · {item.positionName}</h3>
          <small>{interviewStage(item.round)}</small>
        </div>
        <div className="interview-record-result"><StatusBadge value={interviewResultLabel(item.result)} /></div>
      </header>

      <div className="interview-record-meta">
        <span><CalendarClock size={14} /><strong>{item.interviewTime ? formatDateTime(item.interviewTime) : "面试时间待补充"}</strong></span>
        <span><Video size={14} /><strong>{item.interviewMode || "面试形式待补充"}</strong></span>
      </div>

      {scheduleNotes && <p className="interview-record-schedule" title={scheduleNotes}>{scheduleNotes}</p>}

      <div className="interview-record-links">
        {item.meetingLink ? <a href={item.meetingLink} target="_blank" rel="noreferrer"><ExternalLink size={14} />打开会议入口</a> : <span className="interview-record-no-link">暂未添加会议入口</span>}
      </div>

      {item.summary ? <p className="interview-record-summary" title={item.summary}>{item.summary}</p> : <p className="interview-record-summary interview-record-summary-empty">尚未补充整体总结</p>}

      {hasReview ? (
        <details className="interview-review">
          <summary><span>完整复盘</span></summary>
          <div className="interview-review-content">
            {item.summary && <ReviewSection title="整体总结" value={item.summary} />}
            {item.questions && <ReviewSection title="主要问题" value={item.questions} />}
            {item.weakPoints && <ReviewSection title="薄弱点" value={item.weakPoints} />}
            {item.followUp && <ReviewSection title="后续行动" value={item.followUp} />}
          </div>
        </details>
      ) : <p className="interview-review-empty">尚未补充复盘</p>}

      <div className="interview-record-actions"><button type="button" className="text-button" onClick={onEdit}><Pencil size={14} />编辑</button><ConfirmButton className="text-button danger-text" confirmText="删除这条面试记录？" onConfirm={async () => { await api(`/interviews/${item.id}`, { method: "DELETE" }); await refresh(); }}><Trash2 size={14} />删除</ConfirmButton></div>
    </article>
  );
}

function ReviewSection({ title, value }: { title: string; value: string }) {
  return <section><h4>{title}</h4><p>{value}</p></section>;
}

function sortActive(records: Interview[]) {
  return [...records].sort((a, b) => {
    const resultRank = { 待面试: 0, 待确认: 1 } as Record<string, number>;
    const resultOrder = (resultRank[a.result] ?? 9) - (resultRank[b.result] ?? 9);
    if (resultOrder) return resultOrder;
    return compareInterviewTime(a, b, a.result === "待确认" ? "desc" : "asc");
  });
}

function sortHistory(records: Interview[]) {
  return [...records].sort((a, b) => compareInterviewTime(a, b, "desc"));
}

function compareInterviewTime(a: Interview, b: Interview, direction: "asc" | "desc") {
  const aTime = parseTimestamp(a.interviewTime);
  const bTime = parseTimestamp(b.interviewTime);
  if (aTime === null && bTime !== null) return 1;
  if (aTime !== null && bTime === null) return -1;
  if (aTime !== null && bTime !== null && aTime !== bTime) return direction === "asc" ? aTime - bTime : bTime - aTime;
  const aCreated = parseTimestamp(a.createdAt) ?? 0;
  const bCreated = parseTimestamp(b.createdAt) ?? 0;
  return bCreated - aCreated;
}

function parseTimestamp(value?: string) {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function toDateTimeLocal(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
