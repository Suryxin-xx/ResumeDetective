import { ArrowRight, BriefcaseBusiness, CheckCircle2, Clock3, MessageSquareText, TrendingUp } from "lucide-react";
import { api, formatDateTime } from "../api";
import { EmptyState, PageHeader, Panel, StatusBadge } from "../components";
import type { PageProps } from "../App";
import type { Application } from "../types";

const terminalStatuses = new Set(["Offer", "终止"]);
const stageGroups = [
  { label: "投递与初筛", keys: ["已投递", "简历筛选"], filter: "投递与初筛" },
  { label: "测评与笔试", keys: ["测评", "AI 面试", "笔试"], filter: "测评与笔试" },
  { label: "面试推进", keys: ["业务面试", "HR 面"], filter: "面试阶段" },
  { label: "Offer", keys: ["Offer"], filter: "Offer" },
  { label: "已终止", keys: ["终止"], filter: "终止" },
];

function daysSince(value: string) { const time = new Date(value).getTime(); return Number.isFinite(time) ? Math.max(0, Math.floor((Date.now() - time) / 86_400_000)) : 0; }
function suggestedAction(item: Application) {
  if (item.nextAction) return item.nextAction;
  if (["测评", "AI 面试", "笔试"].includes(item.currentStatus)) return "确认是否已完成并更新结果";
  if (["业务面试", "HR 面"].includes(item.currentStatus)) return "记录复盘或跟进面试结果";
  return "确认招聘系统中的最新进度";
}

export default function OverviewV2Page({ data, go, refresh }: PageProps) {
  const active = data.applications.filter((item) => !terminalStatuses.has(item.currentStatus));
  const stalled = active.map((item) => ({ item, days: daysSince(item.statusUpdateTime) })).filter(({ days }) => days >= 5).sort((a, b) => b.days - a.days);
  const health = active.length ? Math.max(0, Math.round(((active.length - stalled.length) / active.length) * 100)) : 100;
  const recent = [...data.applications].sort((a, b) => new Date(b.statusUpdateTime).getTime() - new Date(a.statusUpdateTime).getTime()).slice(0, 6);
  const grouped = stageGroups.map((group) => ({ ...group, count: group.keys.reduce((sum, key) => sum + (data.dashboard.stageCounts[key] || 0), 0) }));
  const maxStage = Math.max(1, ...grouped.map((item) => item.count));
  return <>
    <PageHeader title={data.settings?.config.workspaceName || "秋招工作台"} description="把注意力留给停滞机会与最近变化，不再用待办数量制造焦虑。" />
    {data.dashboard.demo && <div className="demo-banner"><div><strong>你正在查看虚构的演示工作台</strong><span>准备记录真实信息时，可以安全清除全部演示数据。</span></div><button className="secondary-button" onClick={async()=>{if(!confirm("清除发布包内置的全部演示数据？"))return;await api("/demo",{method:"DELETE"});await refresh();}}>清除演示数据</button></div>}
    <section className="health-grid">
      <article className="health-primary"><div className="health-copy"><span>流程健康度</span><strong>{health}<small>%</small></strong><p>{stalled.length ? `${stalled.length} 个岗位超过 5 天没有状态变化，建议集中确认一次。` : "当前流程更新及时，没有明显停滞岗位。"}</p></div><div className="health-ring" style={{"--health": `${health * 3.6}deg`} as React.CSSProperties}><span>{health}</span></div></article>
      <button className="metric-card" onClick={()=>go("applications")}><BriefcaseBusiness/><span>全部投递</span><strong>{data.dashboard.total}</strong><small>{data.dashboard.active} 个仍在流程中</small></button>
      <button className="metric-card" onClick={()=>go("applications?status=面试阶段")}><MessageSquareText/><span>面试阶段</span><strong>{data.dashboard.interview}</strong><small>查看正在面试的投递</small></button>
      <button className="metric-card metric-positive" onClick={()=>go("offers")}><CheckCircle2/><span>Offer</span><strong>{data.dashboard.offers}</strong><small>进入横向对比与决策</small></button>
    </section>
    <div className="overview-main-grid">
      <Panel title="停滞岗位" description="按最后状态更新时间排序；这里只显示仍在流程中的岗位。" action={<button className="text-button" onClick={()=>go("applications")}>打开投递管理 <ArrowRight size={14}/></button>}>
        {stalled.length ? <div className="stalled-table"><div className="stalled-head"><span>公司 / 岗位</span><span>停留环节</span><span>未更新</span><span>建议动作</span></div>{stalled.slice(0,8).map(({item,days})=><button key={item.id} onClick={()=>go(`applications?application=${item.id}`)}><span><strong>{item.companyName}</strong><small>{item.positionName}</small></span><StatusBadge value={item.currentStatus}/><em>{days} 天</em><span className="stalled-action">{suggestedAction(item)}<ArrowRight size={14}/></span></button>)}</div> : <EmptyState title="流程更新很及时" description="超过 5 天没有变化的进行中岗位会自动出现在这里。"/>}
      </Panel>
      <Panel title="阶段分布" description="点击阶段即可查看对应投递。"><div className="stage-bars">{grouped.map(item=><button key={item.label} onClick={()=>go(`applications?status=${encodeURIComponent(item.filter)}`)}><span><strong>{item.label}</strong><em>{item.count}</em></span><i><b style={{width:`${(item.count/maxStage)*100}%`}}/></i></button>)}</div></Panel>
    </div>
    <Panel title="最近状态变化" description="按更新时间排列，终止岗位也保留最后一次变化。" action={<span className="panel-hint"><TrendingUp size={14}/>最近 {recent.length} 条</span>}>
      {recent.length ? <div className="recent-table recent-compact"><div className="recent-head"><span>公司 / 岗位</span><span>当前环节</span><span>最近流转</span><span>更新时间</span></div>{recent.map(item=><button key={item.id} onClick={()=>go(`applications?application=${item.id}`)}><span><strong>{item.companyName}</strong><small>{item.positionName}</small></span><StatusBadge value={item.currentStatus}/><span className="flow-summary">{item.statusHistory.at(-1)?.from ? `${item.statusHistory.at(-1)?.from} → ${item.currentStatus}` : item.stageState}</span><time><Clock3 size={13}/>{formatDateTime(item.statusUpdateTime)}</time></button>)}</div> : <EmptyState title="还没有投递记录" description="新建第一条投递后，状态变化会显示在这里。"/>}
    </Panel>
  </>;
}
