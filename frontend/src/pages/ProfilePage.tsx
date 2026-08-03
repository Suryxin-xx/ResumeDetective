import { useEffect, useState } from "react";
import { BookOpenText, PencilLine, Plus, Save, Trash2 } from "lucide-react";
import { api, jsonBody } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel } from "../components";
import type { PageProps } from "../App";
import type { Material, Profile } from "../types";

const types = ["项目经历", "实习经历", "校园经历", "获奖经历", "技能证书", "其他"];

export default function ProfilePage({data,refresh}:PageProps) {
  const [profile,setProfile]=useState<Profile>(data.profile);
  const [editing,setEditing]=useState<Material|"new"|null>(null);
  const [busy,setBusy]=useState(false);
  useEffect(()=>setProfile(data.profile),[data.profile]);

  async function saveProfile(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);
    try{await api("/profile",{method:"PUT",...jsonBody(profile)});await refresh();window.alert("个人资料已保存。后续 AI 分析会自动引用与岗位有关的内容。");}
    catch(reason){window.alert(reason instanceof Error?reason.message:"保存失败");}finally{setBusy(false)}
  }
  async function saveMaterial(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();const payload=Object.fromEntries(new FormData(event.currentTarget));
    try{if(editing==="new")await api("/materials",{method:"POST",...jsonBody(payload)});else if(editing)await api(`/materials/${editing.id}`,{method:"PATCH",...jsonBody(payload)});setEditing(null);await refresh();}
    catch(reason){window.alert(reason instanceof Error?reason.message:"保存失败")}
  }
  const change=(key:keyof Profile,value:string)=>setProfile({...profile,[key]:value});
  return <>
    <PageHeader eyebrow="CANDIDATE LIBRARY" title="个人资料与经历库" description="只维护一次，JD 匹配、简历建议和面试准备会自动使用这些真实素材。" action={<button className="primary-button" onClick={()=>setEditing("new")}><Plus size={17}/>添加经历</button>}/>
    <div className="profile-layout">
      <Panel title="个人档案" description="先维护稳定信息；AI 默认不发送手机号、出生日期等敏感字段。">
        <form onSubmit={saveProfile}><div className="settings-form profile-form">
          <Field label="姓名"><input value={profile.fullName} onChange={e=>change("fullName",e.target.value)}/></Field><Field label="目标方向"><input value={profile.targetRole} onChange={e=>change("targetRole",e.target.value)} placeholder="后端开发 / 供应链"/></Field>
          <Field label="学历"><input value={profile.education} onChange={e=>change("education",e.target.value)}/></Field><Field label="学校"><input value={profile.school} onChange={e=>change("school",e.target.value)}/></Field>
          <Field label="专业"><input value={profile.major} onChange={e=>change("major",e.target.value)}/></Field><Field label="所在城市"><input value={profile.city} onChange={e=>change("city",e.target.value)}/></Field>
          <Field label="邮箱"><input type="email" value={profile.email} onChange={e=>change("email",e.target.value)}/></Field><Field label="GitHub"><input type="url" value={profile.githubUrl} onChange={e=>change("githubUrl",e.target.value)}/></Field>
          <Field label="作品集链接" span><input type="url" value={profile.portfolioUrl} onChange={e=>change("portfolioUrl",e.target.value)}/></Field><Field label="个人概述" span hint="写清方向、优势和边界；不要为了匹配 JD 虚构经历。"><textarea rows={5} value={profile.summary} onChange={e=>change("summary",e.target.value)}/></Field>
        </div><div className="modal-actions"><button className="primary-button" disabled={busy}><Save size={16}/>{busy?"保存中…":"保存个人资料"}</button></div></form>
      </Panel>
      <Panel title={`经历素材 · ${data.materials.length}`} description="每张卡片保留一段可复用的真实经历，点击即可编辑。" action={<button className="text-button" onClick={()=>setEditing("new")}><Plus size={15}/>添加经历</button>}>
        {data.materials.length?<div className="material-grid">{data.materials.map(item=><button type="button" className="material-card" key={item.id} onClick={()=>setEditing(item)}><div className="material-card-top"><span>{item.materialType}</span><small>{[item.startTime,item.endTime].filter(Boolean).join(" — ")||"未填写时间"}</small></div><h3>{item.title}</h3><p>{item.content}</p><footer><div>{item.tags.split(/[,，]/).map(tag=>tag.trim()).filter(Boolean).slice(0,4).map(tag=><span key={tag}>{tag}</span>)}</div><em>编辑 <PencilLine size={13}/></em></footer></button>)}</div>:<EmptyState title="还没有经历素材" description="先添加最熟悉的一段项目或实习经历，之后 AI 分析就不必反复粘贴。" action={<button className="secondary-button" onClick={()=>setEditing("new")}><BookOpenText size={16}/>添加第一条</button>}/>}</Panel>
    </div>
    {editing&&<Modal title={editing==="new"?"添加经历素材":"编辑经历素材"} subtitle="只记录可在面试中自洽说明的真实信息。" onClose={()=>setEditing(null)} wide><form onSubmit={saveMaterial}><div className="modal-form-grid">
      <Field label="类型"><select name="materialType" defaultValue={editing==="new"?"项目经历":editing.materialType}>{types.map(v=><option key={v}>{v}</option>)}</select></Field><Field label="标题"><input name="title" required autoFocus defaultValue={editing==="new"?"":editing.title}/></Field>
      <Field label="开始时间"><input name="startTime" type="month" defaultValue={editing==="new"?"":editing.startTime}/></Field><Field label="结束时间"><input name="endTime" type="month" defaultValue={editing==="new"?"":editing.endTime}/></Field>
      <Field label="标签" span><input name="tags" defaultValue={editing==="new"?"":editing.tags} placeholder="Java, 数据分析, 跨部门协作"/></Field><Field label="事实与成果" span><textarea name="content" required rows={10} defaultValue={editing==="new"?"":editing.content} placeholder="背景、你的职责、关键动作、量化结果、可复盘的问题…"/></Field>
    </div><div className="modal-actions">{editing!=="new"&&<ConfirmButton confirmText={`确定删除“${editing.title}”？`} onConfirm={async()=>{await api(`/materials/${editing.id}`,{method:"DELETE"});setEditing(null);await refresh();}}><Trash2 size={15}/>删除</ConfirmButton>}<span className="action-spacer"/><button type="button" className="secondary-button" onClick={()=>setEditing(null)}>取消</button><button className="primary-button">保存经历</button></div></form></Modal>}
  </>
}
