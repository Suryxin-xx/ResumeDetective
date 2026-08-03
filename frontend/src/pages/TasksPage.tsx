import { useState } from "react";
import { Check, Plus, RotateCcw, Trash2 } from "lucide-react";
import { api, jsonBody, todayISO } from "../api";
import { ConfirmButton, EmptyState, Field, PageHeader, Panel, Priority } from "../components";
import type { PageProps } from "../App";

export default function TasksPage({ data, refresh }: PageProps) {
  const [showDone, setShowDone] = useState(false);
  const open = data.tasks.filter((item) => item.state === "open"); const done = data.tasks.filter((item) => item.state === "done");
  async function create(event: React.FormEvent<HTMLFormElement>) { event.preventDefault(); const form=event.currentTarget; const payload=Object.fromEntries(new FormData(form)); payload.priority=Number(payload.priority) as never; try{await api("/tasks",{method:"POST",...jsonBody(payload)});form.reset();await refresh();}catch(reason){window.alert(reason instanceof Error?reason.message:"保存失败");} }
  async function state(id:number,value:"open"|"done"){await api(`/tasks/${id}/state`,{method:"PATCH",...jsonBody({state:value})});await refresh();}
  return <><PageHeader eyebrow="ACTION LIST" title="行动清单" description="把准备任务拆小，完成一件就少一件。" />
    <Panel title="快速添加" description="只填任务名也可以，日期和优先级随时调整。"><form className="quick-create" onSubmit={create}><Field label="任务"><input name="title" required placeholder="例如：复习 MySQL 索引" /></Field><Field label="计划日期"><input name="dueDate" type="date" min={todayISO()} /></Field><Field label="优先级"><select name="priority" defaultValue="0">{[0,1,2,3,4,5].map(v=><option key={v} value={v}>{v?`${v} 级`:"普通"}</option>)}</select></Field><Field label="备注"><input name="notes" /></Field><button className="primary-button"><Plus size={16}/>添加</button></form></Panel>
    <Panel title="未完成" description={`${open.length} 项需要处理`}>{open.length?<div className="task-list">{open.map(item=><article key={item.id}><button className="task-complete" onClick={()=>void state(item.id,"done")} title="标记完成"><Check size={16}/></button><div><strong>{item.title}</strong><p>{item.notes||"没有补充备注"}</p><small>{item.dueDate?`计划 ${item.dueDate}`:"未设置日期"}</small></div><Priority value={item.priority}/>{item.source==="manual"&&<ConfirmButton className="icon-button danger-icon" confirmText="删除这条待办？" onConfirm={async()=>{await api(`/tasks/${item.id}`,{method:"DELETE"});await refresh();}}><Trash2 size={15}/></ConfirmButton>}</article>)}</div>:<EmptyState title="今天没有积压" description="保持这个节奏，或者添加一项下一步行动。"/>}</Panel>
    <Panel title="已完成" action={<button className="text-button" onClick={()=>setShowDone(v=>!v)}>{showDone?"收起":`展开 ${done.length} 项`}</button>}>{showDone&&(done.length?<div className="task-list completed-list">{done.map(item=><article key={item.id}><button className="task-complete done" onClick={()=>void state(item.id,"open")} title="恢复"><RotateCcw size={15}/></button><div><strong>{item.title}</strong><small>{item.dueDate||"已完成"}</small></div></article>)}</div>:<EmptyState title="暂无完成记录" description="完成的任务会收纳在这里。"/>)}</Panel>
  </>;
}
