import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FilePenLine, FileText, FolderSearch, LayoutGrid, Link2, List, Search, WandSparkles } from "lucide-react";
import { api } from "../api";
import { EmptyState, PageHeader, Panel, StatusBadge } from "../components";
import type { PageProps } from "../App";
import type { Application } from "../types";

type ResumeGroup = { key: string; actualName: string; displayName: string; path: string; applications: Application[] };
const fileName = (path: string) => path.split(/[\\/]/).pop() || "尚未绑定简历";
const preferredName = (apps: Application[]) => apps.length === 1 ? `${apps[0].companyName} · ${apps[0].positionName}` : `${apps[0].companyName} · ${apps[0].positionName} 等 ${apps.length} 个岗位`;

export default function ResumesLibraryPage({ data, refresh }: PageProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const [view, setView] = useState<"list" | "card">(() => localStorage.getItem("resume-view") === "card" ? "card" : "list");
  const [renaming, setRenaming] = useState<string | null>(null);
  useEffect(() => localStorage.setItem("resume-view", view), [view]);
  const groups = useMemo(() => {
    const map = new Map<string, ResumeGroup>();
    data.applications.forEach((app) => {
      const key = app.resumePath ? app.resumePath.toLowerCase() : `unbound-${app.id}`;
      const current = map.get(key) || { key, actualName: fileName(app.resumePath), displayName: "", path: app.resumePath, applications: [] };
      current.applications.push(app);
      map.set(key, current);
    });
    return Array.from(map.values()).map((group) => ({ ...group, displayName: preferredName(group.applications) }));
  }, [data.applications]);
  const categories = useMemo(() => ["全部", ...Array.from(new Set(data.applications.map((app) => app.category).filter(Boolean)))], [data.applications]);
  const filtered = groups.filter((group) => {
    const text = `${group.actualName} ${group.displayName} ${group.applications.map((app) => `${app.companyName} ${app.positionName} ${app.tags}`).join(" ")}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (category === "全部" || group.applications.some((app) => app.category === category));
  });
  const boundGroups=groups.filter(group=>group.path);const unboundCount=data.applications.filter(app=>!app.resumePath).length;
  async function rename(group:ResumeGroup){if(!group.path)return;setRenaming(group.key);try{const result=await api<{renamed:boolean;fileName:string}>(`/applications/${group.applications[0].id}/resume/rename`,{method:"POST"});await refresh();if(!result.renamed)window.alert(`文件名已经符合规则：${result.fileName}`);}catch(reason){window.alert(reason instanceof Error?reason.message:"重命名失败")}finally{setRenaming(null)}}
  async function renameAll(){if(!boundGroups.length||!window.confirm(`按当前规则整理 ${boundGroups.length} 个简历文件？只处理 data/resumes 内的文件，重名时会自动添加序号。`))return;setRenaming("all");let renamed=0;const failures:string[]=[];for(const group of boundGroups){try{const result=await api<{renamed:boolean}>(`/applications/${group.applications[0].id}/resume/rename`,{method:"POST"});if(result.renamed)renamed++;}catch(reason){failures.push(`${group.displayName}：${reason instanceof Error?reason.message:"失败"}`)}}await refresh();setRenaming(null);window.alert(`整理完成：${renamed} 个文件已重命名${failures.length?`，${failures.length} 个未处理。\n${failures.slice(0,3).join("\n")}`:"。"}`)}
  return <>
    <PageHeader title="简历汇总" description="先按公司与岗位识别，再查看真实文件名；关联岗位与简历都可直接打开。" action={<button className="secondary-button" disabled={Boolean(renaming)||!boundGroups.length} onClick={()=>void renameAll()}><WandSparkles size={15}/>{renaming==="all"?"整理中…":"按规则整理全部"}</button>} />
    <section className="resume-summary-strip"><span><strong>{boundGroups.length}</strong> 个已绑定文件</span><span><strong>{data.applications.length-unboundCount}</strong> 条已关联投递</span><span className={unboundCount?"needs-attention":""}><strong>{unboundCount}</strong> 条未绑定</span><small>命名规则：{data.settings?.config.resumeNameTemplate||"{company}-{position}"}</small></section>
    <Panel className="filter-panel"><div className="filter-row"><label className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件、公司、岗位或标签" /></label><select className="compact-select" value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((value) => <option key={value}>{value}</option>)}</select><span className="result-count">{filtered.length} 个简历版本</span><div className="view-switch"><button className={view === "list" ? "active" : ""} onClick={() => setView("list")}><List size={15} />列表</button><button className={view === "card" ? "active" : ""} onClick={() => setView("card")}><LayoutGrid size={15} />卡片</button></div></div></Panel>
    <Panel className="resume-panel">{filtered.length ? <div className={`resume-file-library ${view}`}>{filtered.map((group) => <article className="resume-file-card" key={group.key}>
      <header><span className={`resume-file-symbol ${group.path ? "" : "empty"}`}><FileText size={22} /></span><div className="resume-file-identity"><h3>{group.displayName}</h3><p title={group.actualName}>{group.path ? group.actualName : "尚未绑定简历文件"}</p></div><div className="resume-primary-actions">{group.path&&<a href={`/resume/${group.applications[0].id}`} target="_blank" rel="noreferrer" className="primary-button">打开简历 <ExternalLink size={14}/></a>}<button type="button" className="icon-button" disabled={!group.path||Boolean(renaming)} onClick={()=>void rename(group)} title="按设置中的规则重命名"><FilePenLine size={15}/></button></div></header>
      <div className="resume-file-tags">{Array.from(new Set(group.applications.flatMap((app) => [app.category, ...app.tags.split(/[,，]/)]).map((value) => value.trim()).filter(Boolean))).slice(0, 6).map((tag) => <span key={tag}>{tag}</span>)}</div>
      <details open={view === "list"}><summary><span>关联投递</span><strong>{group.applications.length}</strong></summary><div className="resume-linked-jobs">{group.applications.map((app) => <div key={app.id}><span><strong>{app.companyName}</strong><small>{app.positionName}</small></span><StatusBadge value={app.currentStatus} /><span className="resume-linked-actions">{group.path&&<a href={`/resume/${app.id}`} target="_blank" rel="noreferrer" title="打开该投递绑定的简历"><FileText size={14}/></a>}{app.jobLink&&<a href={app.jobLink} target="_blank" rel="noreferrer" title="打开岗位链接"><Link2 size={14}/></a>}</span></div>)}</div></details>
    </article>)}</div> : <EmptyState title="没有符合条件的简历" description="在投递详情中绑定 PDF、DOC 或 DOCX。" action={<span className="empty-inline"><FolderSearch size={16} />可以先清除筛选再查看</span>} />}</Panel>
  </>;
}
