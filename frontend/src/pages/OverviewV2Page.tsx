import { ArrowRight, BriefcaseBusiness, CalendarClock, CheckCircle2, Clock3, ExternalLink, MessageSquareText, TimerReset, TrendingUp, Video } from "lucide-react";
import { api, formatDateTime } from "../api";
import { EmptyState, PageHeader, Panel, StatusBadge } from "../components";
import { stageStateLabel } from "../applicationProgress";
import { interviewProgressLabel, preferredInterview } from "../interviewProgress";
import type { PageProps } from "../App";
import type { Application, Interview } from "../types";

const terminalStatuses = new Set(["Offer", "终止", "已终止", "未通过", "主动放弃", "流程结束"]);
const interviewStatuses = new Set(["业务面试", "HR 面"]);
const stageGroups = [
  { label: "投递与初筛", keys: ["已投递", "简历筛选"], filter: "投递与初筛" },
  { label: "测评与笔试", keys: ["测评", "AI 面试", "笔试"], filter: "测评与笔试" },
  { label: "面试推进", keys: ["业务面试", "HR 面"], filter: "面试阶段" },
  { label: "Offer", keys: ["Offer"], filter: "Offer" },
  { label: "已终止", keys: ["终止", "已终止", "未通过", "主动放弃", "流程结束"], filter: "终止" },
];

function daysSince(value: string) { const time = new Date(value).getTime(); return Number.isFinite(time) ? Math.max(0, Math.floor((Date.now() - time) / 86_400_000)) : 0; }

export default function OverviewV2Page({ data, go, refresh }: PageProps) {
  const active = data.applications.filter((item) => !terminalStatuses.has(item.currentStatus));
  const waitingCompany = active.filter(item=>item.stageState==="已完成，等待结果");
  const longWaiting = waitingCompany.filter(item=>daysSince(item.statusUpdateTime)>=7).length;
  const recent = [...data.applications].sort((a, b) => new Date(b.statusUpdateTime).getTime() - new Date(a.statusUpdateTime).getTime()).slice(0, 6);
  const interviewMap = new Map<number, Interview[]>();
  data.interviews.forEach((interview) => interviewMap.set(interview.applicationId, [...(interviewMap.get(interview.applicationId) || []), interview]));
  const currentInterviewMap = new Map(Array.from(interviewMap, ([applicationId, records]) => [applicationId, preferredInterview(records)]));
  const focusInterviews = active.map((item) => ({ item, interview: preferredInterview(interviewMap.get(item.id) || []) })).filter(({ item, interview }) => {
    if (interviewStatuses.has(item.currentStatus)) return true;
    if (!interview) return false;
    const interviewTime = interview.interviewTime ? new Date(interview.interviewTime).getTime() : Number.NaN;
    return interview.result === "待面试" || interview.result === "待确认" || (Number.isFinite(interviewTime) && interviewTime >= Date.now());
  }).sort((a, b) => {
    const aTime = a.interview?.interviewTime ? new Date(a.interview.interviewTime).getTime() : Number.MAX_SAFE_INTEGER;
    const bTime = b.interview?.interviewTime ? new Date(b.interview.interviewTime).getTime() : Number.MAX_SAFE_INTEGER;
    return aTime - bTime || b.item.priority - a.item.priority;
  });
  const visibleFocusInterviews = focusInterviews.slice(0, 4);
  const hiddenFocusInterviewCount = Math.max(0, focusInterviews.length - visibleFocusInterviews.length);
  const grouped = stageGroups.map((group) => ({ ...group, count: group.keys.reduce((sum, key) => sum + (data.dashboard.stageCounts[key] || 0), 0) }));
  const maxStage = Math.max(1, ...grouped.map((item) => item.count));
  const pulse = [
    {value:"待处理",label:"待我处理",description:"测评、材料或准备还没完成",count:active.filter(item=>item.stageState==="待处理").length},
    {value:"已安排",label:"已安排时间",description:"已经定好时间，等待进行",count:active.filter(item=>item.stageState==="已安排").length},
    {value:"已完成，等待结果",label:"等待公司结果",description:longWaiting?`${longWaiting} 个已超过 7 天未变化`:"当前没有长期停滞",count:waitingCompany.length},
  ];
  return <>
    <PageHeader title={data.settings?.config.workspaceName || "秋招工作台"} description="先看近期面试，再判断现在是你要行动，还是等待公司推进。" />
    {data.dashboard.demo && <div className="demo-banner"><div><strong>你正在查看虚构的演示工作台</strong><span>准备记录真实信息时，可以安全清除全部演示数据。</span></div><button className="secondary-button" onClick={async()=>{if(!confirm("清除发布包内置的全部演示数据？"))return;await api("/demo",{method:"DELETE"});await refresh();}}>清除演示数据</button></div>}
    <section className="overview-metrics" aria-label="投递概览">
      <button className="metric-card" onClick={()=>go("applications")}><BriefcaseBusiness/><span>全部投递</span><strong>{data.dashboard.total}</strong><small>查看全部岗位</small></button>
      <button className="metric-card" onClick={()=>go("applications?status=流程中")}><TimerReset/><span>进行中</span><strong>{data.dashboard.active}</strong><small>{waitingCompany.length ? `${waitingCompany.length} 个等待公司结果` : "暂无等待结果的岗位"}</small></button>
      <button className="metric-card" onClick={()=>go("applications?status=面试阶段")}><MessageSquareText/><span>面试阶段</span><strong>{data.dashboard.interview}</strong><small>查看正在面试的投递</small></button>
      <button className="metric-card metric-positive" onClick={()=>go("offers")}><CheckCircle2/><span>Offer</span><strong>{data.dashboard.offers}</strong><small>进入横向对比与决策</small></button>
    </section>
    {focusInterviews.length > 0 && <Panel className="interview-focus-panel" title="重点面试" description="业务面试、HR 面和已经登记的待面试安排集中显示在这里；先保存邮件里的时间和会议链接。" action={<button className="text-button" onClick={()=>go("interviews")}>查看面试安排与复盘 <ArrowRight size={14}/></button>}>
      <div className="interview-focus-grid">{visibleFocusInterviews.map(({ item, interview }) => <article key={item.id} className={!interview ? "needs-schedule" : interview.result === "待确认" ? "needs-follow-up" : ""}>
        <header><div><span>{interview?.result === "待确认" ? `${interview.round}结果待跟进` : interview ? `${item.currentStatus} · ${interview.round}` : item.currentStatus}</span><h3>{item.companyName}</h3><p>{item.positionName}</p></div><StatusBadge value={interview?.result === "待确认" ? "结果待通知" : interview?.result || item.stageState}/></header>
        <div className="interview-focus-schedule">
          <span><CalendarClock size={15}/><strong>{interview?.interviewTime ? formatDateTime(interview.interviewTime) : "面试时间待补充"}</strong></span>
          <span><Video size={15}/>{interview ? [interview.round, interview.interviewMode].filter(Boolean).join(" · ") || "轮次与形式待补充" : "还没有面试安排记录"}</span>
          {interview?.scheduleNotes && <p>{interview.scheduleNotes}</p>}
        </div>
        <footer><button className="text-button" onClick={()=>go(`applications?application=${item.id}`)}>查看投递</button>{interview?.meetingLink && <a className="secondary-button" href={interview.meetingLink} target="_blank" rel="noreferrer"><ExternalLink size={14}/>进入会议</a>}<button className="primary-button" onClick={()=>go(interview ? `interviews?interview=${interview.id}` : `interviews?application=${item.id}`)}>{interview ? "编辑安排" : "补充面试安排"}</button></footer>
      </article>)}</div>
      {hiddenFocusInterviewCount > 0 && <div className="interview-focus-more"><button className="secondary-button" onClick={()=>go("interviews")}>还有 {hiddenFocusInterviewCount} 条重点面试，查看全部 <ArrowRight size={14}/></button></div>}
    </Panel>}
    <div className="overview-main-grid">
      <Panel className="flow-pulse-panel" title="流程脉搏" description="按责任方归类当前进展，不再用固定的停滞名单占满首页。">
        <div className="flow-pulse-grid">{pulse.map(item=><button key={item.value} onClick={()=>go(`applications?stage=${encodeURIComponent(item.value)}`)}><span>{item.label}</span><strong>{item.count}</strong><small>{item.description}</small><i><ArrowRight size={14}/></i></button>)}</div>
      </Panel>
      <Panel title="招聘阶段" description="点击阶段查看对应岗位。"><div className="stage-bars">{grouped.map(item=><button key={item.label} onClick={()=>go(`applications?status=${encodeURIComponent(item.filter)}`)}><span><strong>{item.label}</strong><em>{item.count}</em></span><i><b style={{width:`${(item.count/maxStage)*100}%`}}/></i></button>)}</div></Panel>
    </div>
    <Panel title="最近变化" description="终止岗位也保留最后一次流转。" action={<span className="panel-hint"><TrendingUp size={14}/>最近 {recent.length} 条</span>}>
      {recent.length ? <div className="recent-table recent-compact"><div className="recent-head"><span>公司 / 岗位</span><span>当前环节</span><span>最近流转</span><span>更新时间</span></div>{recent.map(item=>{const interview=currentInterviewMap.get(item.id);return <button key={item.id} onClick={()=>go(`applications?application=${item.id}`)}><span><strong>{item.companyName}</strong><small>{item.positionName}</small></span><span className="stage-with-round"><StatusBadge value={item.currentStatus}/>{interview&&<small>{interviewProgressLabel(interview)}</small>}</span><span className="flow-summary">{interview&&interviewStatuses.has(item.currentStatus)?interviewProgressLabel(interview):item.statusHistory.at(-1)?.from ? `${item.statusHistory.at(-1)?.from} → ${item.currentStatus}` : stageStateLabel(item.stageState)}</span><time><Clock3 size={13}/>{formatDateTime(item.statusUpdateTime)}</time></button>})}</div> : <EmptyState title="还没有投递记录" description="新建第一条投递后，状态变化会显示在这里。"/>}
    </Panel>
  </>;
}
