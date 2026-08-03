import { useMemo, useState } from "react";
import { ArrowRight, ExternalLink, Plus, Search, Trash2 } from "lucide-react";
import { api, jsonBody, todayISO } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel, Priority, StatusBadge } from "../components";
import type { PageProps } from "../App";
import type { JobTarget } from "../types";

const targetStatuses = ["待研究", "待投递", "已投递", "暂不考虑"];

export default function TargetsPage({ data, refresh, go }: PageProps) {
  const [query, setQuery] = useState(""); const [filter, setFilter] = useState("进行中");
  const [editing, setEditing] = useState<JobTarget | "new" | null>(null); const [converting, setConverting] = useState<JobTarget | null>(null);
  const items = useMemo(() => data.targets.filter((item) => {
    if (query && !`${item.companyName} ${item.positionName} ${item.city} ${item.notes}`.toLowerCase().includes(query.toLowerCase())) return false;
    if (filter === "进行中") return item.status === "待研究" || item.status === "待投递";
    if (filter === "全部") return true;
    return item.status === filter;
  }), [data.targets, query, filter]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget)); payload.priority = Number(payload.priority) as never;
    try {
      if (editing === "new") await api("/targets", { method: "POST", ...jsonBody(payload) });
      else if (editing) await api(`/targets/${editing.id}`, { method: "PATCH", ...jsonBody(payload) });
      setEditing(null); await refresh();
    } catch (reason) { window.alert(reason instanceof Error ? reason.message : "保存失败"); }
  }

  async function convert(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!converting) return;
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const result = await api<{ applicationId: number }>(`/targets/${converting.id}/convert`, { method: "POST", ...jsonBody(payload) });
      setConverting(null); await refresh(); go("applications");
      window.alert(`已创建投递 #${result.applicationId}`);
    } catch (reason) { window.alert(reason instanceof Error ? reason.message : "转换失败"); }
  }

  return <>
    <PageHeader eyebrow="OPPORTUNITY LIST" title="意向清单" description="先收集，再判断；确认投递后保留原始线索。" action={<button className="primary-button" onClick={() => setEditing("new")}><Plus size={17} />添加意向</button>} />
    <Panel className="filter-panel"><div className="filter-row"><label className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司、岗位或备注" /></label><div className="segmented">{["进行中", "待研究", "待投递", "已投递", "暂不考虑", "全部"].map((value) => <button className={filter === value ? "active" : ""} key={value} onClick={() => setFilter(value)}>{value}</button>)}</div></div></Panel>
    <Panel className="table-panel">{items.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>公司 / 岗位</th><th>城市</th><th>状态</th><th>优先级</th><th>备注</th><th aria-label="操作" /></tr></thead><tbody>{items.map((item) => <tr key={item.id} className={item.status === "已投递" || item.status === "暂不考虑" ? "terminal-row" : ""}>
      <td><div className="entity-cell"><span className="company-avatar">{item.companyName.slice(0, 1)}</span><span><strong>{item.companyName}</strong><small>{item.positionName}</small></span></div></td><td>{item.city || "—"}</td><td><StatusBadge value={item.status} /></td><td><Priority value={item.priority} /></td><td><span className="line-clamp">{item.notes || item.jdText || "—"}</span></td><td><div className="row-actions">{item.jdLink && <a className="icon-button" href={item.jdLink} target="_blank" rel="noreferrer" title="打开岗位"><ExternalLink size={15} /></a>}<button className="text-button" onClick={() => setEditing(item)}>编辑</button>{item.status !== "已投递" && <button className="row-toggle" onClick={() => setConverting(item)}>转为投递 <ArrowRight size={14} /></button>}</div></td>
    </tr>)}</tbody></table></div> : <EmptyState title="还没有意向岗位" description="看到值得研究的岗位，先把链接和 JD 留在这里。" action={<button className="secondary-button" onClick={() => setEditing("new")}>添加第一条</button>} />}</Panel>
    {editing && <Modal title={editing === "new" ? "添加意向岗位" : "编辑意向岗位"} subtitle="保存原始 JD，后续岗位下线也不怕。" onClose={() => setEditing(null)} wide><form onSubmit={save}><div className="modal-form-grid"><Field label="公司名称"><input name="companyName" required autoFocus defaultValue={editing === "new" ? "" : editing.companyName} /></Field><Field label="岗位名称"><input name="positionName" required defaultValue={editing === "new" ? "" : editing.positionName} /></Field><Field label="状态"><select name="status" defaultValue={editing === "new" ? "待研究" : editing.status}>{targetStatuses.map((value) => <option key={value}>{value}</option>)}</select></Field><Field label="优先级"><select name="priority" defaultValue={editing === "new" ? 0 : editing.priority}>{[0,1,2,3,4,5].map((value)=><option key={value} value={value}>{value ? `${value} 级` : "普通"}</option>)}</select></Field><Field label="城市"><input name="city" defaultValue={editing === "new" ? "" : editing.city} /></Field><Field label="岗位链接"><input name="jdLink" type="url" defaultValue={editing === "new" ? "" : editing.jdLink} /></Field><Field label="备注" span><textarea name="notes" rows={3} defaultValue={editing === "new" ? "" : editing.notes} /></Field><Field label="JD 原文" span><textarea name="jdText" rows={8} defaultValue={editing === "new" ? "" : editing.jdText} /></Field></div><div className="modal-actions">{editing !== "new" && <ConfirmButton confirmText={`确定删除 ${editing.companyName} · ${editing.positionName}？`} onConfirm={async()=>{await api(`/targets/${editing.id}`,{method:"DELETE"});setEditing(null);await refresh();}}><Trash2 size={15}/>删除</ConfirmButton>}<span className="action-spacer"/><button type="button" className="secondary-button" onClick={()=>setEditing(null)}>取消</button><button className="primary-button">保存</button></div></form></Modal>}
    {converting && <Modal title="转为正式投递" subtitle={`${converting.companyName} · ${converting.positionName}`} onClose={() => setConverting(null)}><form onSubmit={convert}><div className="modal-form-grid single-column"><Field label="投递日期"><input name="appliedAt" type="date" defaultValue={todayISO()} /></Field><Field label="投递来源"><input name="source" placeholder="官网 / 内推" /></Field><Field label="岗位类型"><input name="category" placeholder="研发 / 供应链 / 产品" /></Field><Field label="自定义标签"><input name="tags" placeholder="新能源, 管培" /></Field><input name="resumePath" type="hidden" value="" /></div><div className="modal-note">转换后会创建“已投递”记录，并在意向清单保留一条“已投递”来源记录。</div><div className="modal-actions"><button type="button" className="secondary-button" onClick={()=>setConverting(null)}>取消</button><button className="primary-button">确认转为投递</button></div></form></Modal>}
  </>;
}
