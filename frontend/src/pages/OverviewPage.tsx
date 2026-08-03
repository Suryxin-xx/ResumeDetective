import { ArrowRight, BriefcaseBusiness, CheckCircle2, CircleDot, ListTodo, Sparkles } from "lucide-react";
import { api, formatDateTime } from "../api";
import { EmptyState, PageHeader, Panel, StatusBadge } from "../components";
import type { PageProps } from "../App";

const terminalStatuses = new Set(["Offer", "终止"]);

export default function OverviewPage({ data, go, refresh }: PageProps) {
  const recent = data.applications.slice(0, 6);
  const pendingTargets = data.targets.filter((item) => item.status === "待投递");
  const openTasks = data.tasks.filter((item) => item.state === "open");
  const actionApplications = data.applications.filter((item) => !terminalStatuses.has(item.currentStatus)
    && (item.stageState === "待处理" || item.stageState === "已安排" || item.stageState === "进行中" || item.nextAction));
  const attention = [
    ...openTasks.map((item) => ({ key: `task-${item.id}`, kind: "行动", title: item.title, detail: item.dueDate ? `计划 ${item.dueDate}` : "未设置日期", page: "tasks" })),
    ...actionApplications.map((item) => ({ key: `app-${item.id}`, kind: "流程", title: `${item.companyName} · ${item.positionName}`, detail: item.nextAction || `${item.currentStatus} · ${item.stageState}`, page: "applications" })),
    ...pendingTargets.map((item) => ({ key: `target-${item.id}`, kind: "投递", title: `${item.companyName} · ${item.positionName}`, detail: item.city || "意向清单待确认", page: "targets" })),
  ].slice(0, 5);
  const attentionTotal = openTasks.length + actionApplications.length + pendingTargets.length;
  const groupedProgress = [
    { label: "投递与初筛", note: "已投递、简历筛选", count: (data.dashboard.stageCounts["已投递"] || 0) + (data.dashboard.stageCounts["简历筛选"] || 0) },
    { label: "测评与笔试", note: "测评、AI 面试、笔试", count: (data.dashboard.stageCounts["测评"] || 0) + (data.dashboard.stageCounts["AI 面试"] || 0) + (data.dashboard.stageCounts["笔试"] || 0) },
    { label: "面试推进", note: "业务面试、HR 面", count: (data.dashboard.stageCounts["业务面试"] || 0) + (data.dashboard.stageCounts["HR 面"] || 0) },
    { label: "已结束", note: "Offer、终止与归档", count: (data.dashboard.stageCounts["Offer"] || 0) + (data.dashboard.stageCounts["终止"] || 0) },
  ];

  return (
    <>
      <PageHeader eyebrow="OVERVIEW" title={data.settings?.config.workspaceName || "秋招工作台"} description="今天先处理什么、机会推进到哪里，一页看清。" />
      {data.dashboard.demo && <div className="demo-banner"><div><strong>你正在查看虚构的演示工作台</strong><span>准备记录真实信息时，可以安全清除全部演示数据。</span></div><button className="secondary-button" onClick={async()=>{if(!confirm("清除发布包内置的全部演示数据？此操作不会影响后来创建的真实记录。"))return;await api("/demo",{method:"DELETE"});await refresh();}}>清除演示数据</button></div>}

      <section className="overview-hero">
        <div className="focus-copy">
          <p className="eyebrow">TODAY · 今日推进</p>
          <h2>{attentionTotal ? <><strong>{attentionTotal}</strong> 件事需要处理</> : "今天没有必须处理的事项"}</h2>
          <p>{attention.length ? "优先处理有明确动作的投递，再补充尚未转投递的意向岗位。" : "可以整理意向岗位、补全 JD，或回顾最近一次状态变化。"}</p>
          {attention.length ? <div className="focus-queue">{attention.slice(0, 3).map((item) => <button key={item.key} onClick={() => go(item.page)}><span className={`attention-kind kind-${item.kind}`}>{item.kind}</span><span><strong>{item.title}</strong><small>{item.detail}</small></span><ArrowRight size={16}/></button>)}</div> : <button className="secondary-button" onClick={() => go("applications")}>查看全部投递 <ArrowRight size={15}/></button>}
          {attention.length > 3 && <button className="text-button focus-more" onClick={() => go("tasks")}>查看其余 {attention.length - 3} 项 <ArrowRight size={14}/></button>}
        </div>
        <div className="overview-score" aria-label="求职概况">
          <button onClick={() => go("applications")}><BriefcaseBusiness/><span>进行中</span><strong>{data.dashboard.active}</strong></button>
          <button onClick={() => go("tasks")}><ListTodo/><span>待处理</span><strong>{attentionTotal}</strong></button>
          <button onClick={() => go("interviews")}><CircleDot/><span>面试中</span><strong>{data.dashboard.interview}</strong></button>
          <button onClick={() => go("applications")}><CheckCircle2/><span>Offer</span><strong>{data.dashboard.offers}</strong></button>
        </div>
      </section>

      <Panel title="流程位置" description="合并相邻阶段，只保留判断节奏所需的信息。" action={<button className="text-button" onClick={() => go("applications")}>全部投递 <ArrowRight size={14}/></button>}>
        <div className="stage-strip">{groupedProgress.map((item, index) => <button key={item.label} onClick={() => go("applications")}><span className="stage-number">{String(index + 1).padStart(2,"0")}</span><span><strong>{item.label}</strong><small>{item.note}</small></span><em>{item.count}</em></button>)}</div>
      </Panel>

      <Panel title="最近状态变化" description="按更新时间排列，看到岗位和变化即可。" action={<button className="text-button" onClick={() => go("ai")}><Sparkles size={14}/>AI 准备</button>}>
        {recent.length ? <div className="recent-table recent-compact"><div className="recent-head"><span>公司 / 岗位</span><span>最近变化</span><span>更新时间</span></div>{recent.map((item) => <button key={item.id} onClick={() => go("applications")}><span><strong>{item.companyName}</strong><small>{item.positionName}</small></span><span className="recent-change"><StatusBadge value={item.currentStatus}/><small>{item.stageState}</small></span><time>{formatDateTime(item.statusUpdateTime)}</time></button>)}</div> : <EmptyState title="还没有投递记录" description="新建第一条投递后，状态变化会显示在这里。" />}
      </Panel>
    </>
  );
}
