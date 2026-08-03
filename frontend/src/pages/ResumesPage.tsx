import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FileText, LayoutGrid, List, Search } from "lucide-react";
import { EmptyState, PageHeader, Panel, StatusBadge } from "../components";
import type { PageProps } from "../App";

export default function ResumesPage({data}:PageProps){
  const[query,setQuery]=useState("");
  const[category,setCategory]=useState("全部");
  const[view,setView]=useState<"list"|"card">(()=>window.localStorage.getItem("resume-view")==="list"?"list":"card");
  useEffect(()=>window.localStorage.setItem("resume-view",view),[view]);
  const categories=useMemo(()=>["全部",...Array.from(new Set(data.applications.map(a=>a.category).filter(Boolean)))],[data.applications]);
  const items=data.applications.filter(a=>(category==="全部"||a.category===category)&&(!query||`${a.companyName} ${a.positionName} ${a.tags}`.toLowerCase().includes(query.toLowerCase())));
  return <><PageHeader eyebrow="RESUME LIBRARY" title="简历汇总" description="只看岗位、关键词和对应简历，快速找到投递时使用的版本。"/>
    <Panel className="filter-panel"><div className="filter-row"><label className="search-box"><Search size={17}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索公司、岗位或标签"/></label><div className="segmented">{categories.map(v=><button key={v} className={category===v?"active":""} onClick={()=>setCategory(v)}>{v}</button>)}</div><span className="result-count">{items.length} 条记录</span><div className="view-switch" aria-label="简历汇总视图"><button className={view==="list"?"active":""} onClick={()=>setView("list")} title="列表视图"><List size={15}/>列表</button><button className={view==="card"?"active":""} onClick={()=>setView("card")} title="卡片视图"><LayoutGrid size={15}/>卡片</button></div></div></Panel>
    <Panel className="resume-panel">{items.length?(view==="card"?<div className="resume-list resume-card-view">{items.map(item=><ResumeCard key={item.id} item={item}/>)}</div>:<div className="resume-table-view"><div className="resume-table-head"><span>公司 / 岗位</span><span>关键词 / 标签</span><span>当前状态</span><span>对应简历</span><span>操作</span></div>{items.map(item=><article key={item.id}><div className="resume-entity"><span className="resume-file-icon"><FileText size={18}/></span><span><strong>{item.companyName}</strong><small>{item.positionName}</small></span></div><Tags value={item.tags} category={item.category}/><StatusBadge value={item.currentStatus}/><ResumeBinding item={item}/><ResumeActions item={item}/></article>)}</div>):<EmptyState title="没有符合条件的简历" description="在投递详情中绑定 PDF、DOC 或 DOCX。"/>}</Panel>
  </>;
}

function ResumeCard({item}:{item:PageProps["data"]["applications"][number]}){return <article><span className="resume-file-icon"><FileText size={21}/></span><div className="resume-main"><div className="resume-copy"><h3>{item.companyName}<span> / {item.positionName}</span></h3><Tags value={item.tags} category={item.category}/><ResumeBinding item={item}/></div></div><div className="resume-state"><StatusBadge value={item.currentStatus}/></div><ResumeActions item={item}/></article>}
function Tags({value,category}:{value:string;category:string}){const tags=value.split(/[,，]/).map(tag=>tag.trim()).filter(Boolean).slice(0,5);return <div className="tag-row">{category&&<span className="category-tag">{category}</span>}{tags.length?tags.map(tag=><span key={tag}>{tag}</span>):!category&&<span>无标签</span>}</div>}
function ResumeBinding({item}:{item:PageProps["data"]["applications"][number]}){const name=item.resumePath.split(/[\\/]/).pop();return <div className={`resume-binding ${item.resumePath?"bound":"unbound"}`}><FileText size={14}/><span>{name||"尚未绑定简历"}</span></div>}
function ResumeActions({item}:{item:PageProps["data"]["applications"][number]}){return <div className="resume-actions">{item.resumePath&&<a className="secondary-button" href={`/resume/${item.id}`} target="_blank" rel="noreferrer">查看简历 <ExternalLink size={14}/></a>}{item.jobLink&&<a className="icon-button" href={item.jobLink} target="_blank" rel="noreferrer" title="岗位链接"><ExternalLink size={15}/></a>}</div>}
