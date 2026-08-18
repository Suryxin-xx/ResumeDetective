import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness, Building2, CalendarCheck2, FileText, LayoutDashboard, ListTodo,
  MessageSquareText, Settings, Sparkles, Target, Wrench, Plus, PanelLeftClose, PanelLeftOpen, UserRound, BadgeDollarSign,
} from "lucide-react";
import { api } from "./api";
import type { Application, Dashboard, Interview, JobTarget, Material, MigrationStatus, Offer, Profile, SettingsView, SystemInfo, Task } from "./types";
import OverviewPage from "./pages/OverviewV2Page";
import ApplicationsPage from "./pages/ApplicationsPage";
import TargetsPage from "./pages/TargetsPage";
import TasksPage from "./pages/TasksPage";
import InterviewsPage from "./pages/InterviewsPage";
import ResumesPage from "./pages/ResumesLibraryPage";
import AIPage from "./pages/AIPage";
import ToolsPage from "./pages/ToolsPage";
import SettingsPage from "./pages/SettingsPage";
import ProfilePage from "./pages/ProfileV2Page";
import OffersPage from "./pages/OffersPage";

export type DataState = {
  dashboard: Dashboard;
  applications: Application[];
  targets: JobTarget[];
  tasks: Task[];
  interviews: Interview[];
  offers: Offer[];
  profile: Profile;
  materials: Material[];
  settings: SettingsView | null;
  migration: MigrationStatus | null;
  system: SystemInfo | null;
};

const emptyDashboard: Dashboard = { total: 0, active: 0, interview: 0, offers: 0, openTasks: 0, stageCounts: {}, demo: false };

export const navigation = [
  ["overview", "总览", LayoutDashboard],
  ["applications", "投递管理", BriefcaseBusiness],
  ["targets", "意向清单", Target],
  ["tasks", "行动清单", ListTodo],
  ["interviews", "面试复盘", MessageSquareText],
  ["offers", "Offer 对比", BadgeDollarSign],
  ["resumes", "简历汇总", FileText],
  ["profile", "个人资料库", UserRound],
  ["ai", "AI 助手", Sparkles],
  ["tools", "配套工具", Wrench],
  ["settings", "设置", Settings],
] as const;

function routeFromHash() {
  const route = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return navigation.some(([key]) => key === route) ? route : "overview";
}

export default function App() {
  const [page, setPage] = useState(routeFromHash);
  const [sidebarCompact, setSidebarCompact] = useState(false);
  const [newApplicationSignal, setNewApplicationSignal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState<DataState>({ dashboard: emptyDashboard, applications: [], targets: [], tasks: [], interviews: [], offers: [], profile: {id:0,fullName:"",email:"",city:"",education:"",school:"",major:"",targetRole:"",summary:"",githubUrl:"",portfolioUrl:"",updatedAt:""}, materials: [], settings: null, migration: null, system: null });

  const refresh = useCallback(async () => {
    try {
      const [dashboard, applications, targets, tasks, interviews, offers, profile, materials, settings, migration, system] = await Promise.all([
        api<Dashboard>("/dashboard"), api<Application[]>("/applications"), api<JobTarget[]>("/targets"),
        api<Task[]>("/tasks"), api<Interview[]>("/interviews"), api<Offer[]>("/offers"), api<Profile>("/profile"), api<Material[]>("/materials"), api<SettingsView>("/settings"),
        api<MigrationStatus>("/migration/status"), api<SystemInfo>("/system/info"),
      ]);
      setData({ dashboard, applications, targets, tasks, interviews, offers, profile, materials, settings, migration, system });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法连接本地服务");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { document.documentElement.dataset.theme = data.settings?.config.theme || "bright"; }, [data.settings?.config.theme]);
  useEffect(() => {
    const onHash = () => setPage(routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((next: string) => {
    window.location.hash = `/${next}`;
    setPage(next.split("?")[0]);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  const today = useMemo(() => new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long" }).format(new Date()), []);
  const workspaceName = data.settings?.config.workspaceName || "秋招工作台";
  const visibleNavigation = useMemo(() => {
    const configuredOrder = data.settings?.config.navigationOrder || navigation.map(([key]) => key);
    const hidden = new Set(data.settings?.config.hiddenNavigation || []);
    const byKey = new Map<string, (typeof navigation)[number]>(navigation.map((item) => [item[0], item]));
    return configuredOrder
      .map((key) => byKey.get(key))
      .filter((item): item is (typeof navigation)[number] => Boolean(item) && !hidden.has(item![0]));
  }, [data.settings?.config.hiddenNavigation, data.settings?.config.navigationOrder]);

  const pageProps = { data, refresh, go };
  let content;
  switch (page) {
    case "applications": content = <ApplicationsPage {...pageProps} newSignal={newApplicationSignal} consumeNewSignal={() => setNewApplicationSignal(0)} />; break;
    case "targets": content = <TargetsPage {...pageProps} />; break;
    case "tasks": content = <TasksPage {...pageProps} />; break;
    case "interviews": content = <InterviewsPage {...pageProps} />; break;
    case "offers": content = <OffersPage {...pageProps} />; break;
    case "resumes": content = <ResumesPage {...pageProps} />; break;
    case "profile": content = <ProfilePage {...pageProps} />; break;
    case "ai": content = <AIPage {...pageProps} />; break;
    case "tools": content = <ToolsPage {...pageProps} />; break;
    case "settings": content = <SettingsPage {...pageProps} />; break;
    default: content = <OverviewPage {...pageProps} />;
  }

  if (loading) return <div className="startup"><img src="/app-icon-128.png" alt="" /><div><strong>ResumeDetective</strong><span>正在整理你的求职进度…</span></div></div>;
  if (error) return <div className="startup startup-error"><strong>本地工作台暂时不可用</strong><span>{error}</span><button className="primary-button" onClick={() => void refresh()}>重新连接</button></div>;

  return (
    <div className={`app-shell ${sidebarCompact ? "sidebar-compact" : ""}`}>
      <aside className="sidebar">
        <div className="brand-row">
          <img src="/app-icon-64.png" alt="" />
          <div className="brand-copy"><strong>ResumeDetective</strong><span>{workspaceName}</span></div>
        </div>
        <nav aria-label="主导航">
          {visibleNavigation.map(([key, label, Icon]) => (
            <button key={key} className={page === key ? "active" : ""} onClick={() => go(key)} title={sidebarCompact ? label : undefined}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {key === "targets" && data.targets.filter((item) => item.status === "待投递").length > 0 && <em>{data.targets.filter((item) => item.status === "待投递").length}</em>}
              {key === "tasks" && data.dashboard.openTasks > 0 && <em>{data.dashboard.openTasks}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="running-dot" />
          <div><strong>本机服务运行中</strong><small>127.0.0.1:{data.settings?.config.port || 8765}</small></div>
          <button className="sidebar-toggle" aria-label="切换侧栏" onClick={() => setSidebarCompact((value) => !value)}>{sidebarCompact ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}</button>
        </div>
      </aside>
      <main className="main-area">
        <div className="topbar">
          <div className="today"><CalendarCheck2 size={16} /><span>{today}</span></div>
          <button className="primary-button compact-button" onClick={() => { go("applications"); setNewApplicationSignal((value) => value + 1); }}><Plus size={17} />新建投递</button>
        </div>
        <div className="page-container">{content}</div>
        <footer className="app-footer"><span>© Suryxin-xx · ResumeDetective</span><span>本地优先 · 数据保存在 EXE 旁的 data 文件夹</span></footer>
      </main>
    </div>
  );
}

export type PageProps = { data: DataState; refresh: () => Promise<void>; go: (page: string) => void };
