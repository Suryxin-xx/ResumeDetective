import { useMemo, useState } from "react";
import { BadgeDollarSign, CalendarClock, Pencil, Plus, Trash2, TrendingUp } from "lucide-react";
import { api, jsonBody } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel } from "../components";
import type { PageProps } from "../App";
import type { Offer } from "../types";

const scoreFields = [
  ["growthScore", "成长空间"], ["interestScore", "业务兴趣"], ["locationScore", "地点满意"],
  ["stabilityScore", "稳定性"], ["workIntensity", "工作强度"],
] as const;
const decisions = ["考虑中", "倾向接受", "已接受", "已拒绝", "已过期"];
const total = (offer: Offer) => offer.monthlySalary * offer.salaryMonths + offer.bonus + offer.signingBonus + offer.otherCompensation;
const score = (offer: Offer) => Math.round(((offer.growthScore + offer.interestScore + offer.locationScore + offer.stabilityScore + (6 - offer.workIntensity)) / 25) * 100);
const money = (value: number) => value ? `¥${value.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}` : "待填写";

export default function OffersPage({ data, refresh }: PageProps) {
  const [editing, setEditing] = useState<Offer | "new" | null>(null);
  const sorted = useMemo(() => [...data.offers].sort((a,b) => total(b)-total(a)), [data.offers]);
  const candidates = useMemo(() => [...data.applications].sort((a,b) => Number(b.currentStatus === "Offer") - Number(a.currentStatus === "Offer") || a.companyName.localeCompare(b.companyName,"zh-CN")), [data.applications]);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    const numeric = ["applicationId","monthlySalary","salaryMonths","bonus","signingBonus","otherCompensation","workIntensity","growthScore","interestScore","locationScore","stabilityScore"];
    numeric.forEach((key) => { values[key] = Number(values[key]) as never; });
    try { await api("/offers", { method:"PUT", ...jsonBody(values) }); setEditing(null); await refresh(); }
    catch(reason) { window.alert(reason instanceof Error ? reason.message : "Offer 保存失败"); }
  }
  return <>
    <PageHeader title="Offer 对比" description="把薪酬、成长、地点和风险放到同一把尺子上，记录事实，不替你做决定。" action={<button className="primary-button" disabled={!data.applications.length} title={data.applications.length?"为任意投递补充 Offer 信息":"请先新建一条投递"} onClick={()=>setEditing("new")}><Plus size={16}/>添加 Offer 详情</button>}/>
    <section className="offer-summary-grid"><article><BadgeDollarSign/><span>已记录 Offer</span><strong>{data.offers.length}</strong></article><article><TrendingUp/><span>最高总包估算</span><strong>{money(Math.max(0,...data.offers.map(total)))}</strong></article><article><CalendarClock/><span>最近决策截止</span><strong>{data.offers.map(item=>item.deadline).filter(Boolean).sort()[0] || "未填写"}</strong></article></section>
    <Panel title="横向比较" description="总包 = 月薪 × 薪资月数 + 奖金 + 签字费 + 其他现金；评分仅用于辅助回忆。">
      {sorted.length ? <div className="offer-table-wrap"><table className="offer-table"><thead><tr><th>公司 / 岗位</th><th>总包估算</th><th>月薪结构</th><th>综合参考</th><th>决策状态</th><th>截止日期</th><th/></tr></thead><tbody>{sorted.map(offer=><tr key={offer.id}><td><strong>{offer.companyName}</strong><small>{offer.positionName}{offer.department?` · ${offer.department}`:""}</small></td><td className="offer-total">{money(total(offer))}</td><td>{offer.monthlySalary?`${money(offer.monthlySalary)} × ${offer.salaryMonths}`:"待填写"}</td><td><span className="offer-score">{score(offer)}</span></td><td><span className={`decision-badge decision-${offer.decisionStatus}`}>{offer.decisionStatus}</span></td><td>{offer.deadline||"—"}</td><td><button className="row-toggle" onClick={()=>setEditing(offer)}><Pencil size={14}/>编辑</button></td></tr>)}</tbody></table></div> : <EmptyState title="还没有 Offer 详情" description="收到口头或正式 Offer 后即可关联任意投递记录，无需先手动修改投递状态。" action={candidates.length?<button className="secondary-button" onClick={()=>setEditing("new")}>添加第一份 Offer</button>:undefined}/>} 
    </Panel>
    {editing && <Modal title={editing==="new"?"添加 Offer 详情":"编辑 Offer 详情"} subtitle="金额均为税前人民币；不确定的项目可以留空。" onClose={()=>setEditing(null)} wide><form onSubmit={save}><div className="modal-form-grid">
      <Field label="对应岗位" span><select name="applicationId" required defaultValue={editing==="new"?"":editing.applicationId}><option value="" disabled>选择对应投递</option>{candidates.map(app=><option key={app.id} value={app.id}>{app.companyName} · {app.positionName}（{app.currentStatus}）</option>)}</select></Field>
      <Field label="部门 / 业务"><input name="department" defaultValue={editing==="new"?"":editing.department}/></Field><Field label="工作地点"><input name="location" defaultValue={editing==="new"?"":editing.location}/></Field>
      <Field label="税前月薪"><input name="monthlySalary" type="number" min="0" step="0.1" defaultValue={editing==="new"?"":editing.monthlySalary}/></Field><Field label="薪资月数"><input name="salaryMonths" type="number" min="1" step="0.5" defaultValue={editing==="new"?12:editing.salaryMonths}/></Field>
      <Field label="奖金"><input name="bonus" type="number" min="0" step="0.1" defaultValue={editing==="new"?0:editing.bonus}/></Field><Field label="签字费"><input name="signingBonus" type="number" min="0" step="0.1" defaultValue={editing==="new"?0:editing.signingBonus}/></Field>
      <Field label="其他现金"><input name="otherCompensation" type="number" min="0" step="0.1" defaultValue={editing==="new"?0:editing.otherCompensation}/></Field><Field label="接受截止日期"><input name="deadline" type="date" defaultValue={editing==="new"?"":editing.deadline}/></Field>
      {scoreFields.map(([key,label])=><Field label={`${label}（1–5）`} key={key}><select name={key} defaultValue={editing==="new"?3:editing[key]}>{[1,2,3,4,5].map(v=><option value={v} key={v}>{v}</option>)}</select></Field>)}
      <Field label="决策状态"><select name="decisionStatus" defaultValue={editing==="new"?"考虑中":editing.decisionStatus}>{decisions.map(value=><option key={value}>{value}</option>)}</select></Field>
      <Field label="风险、福利与补充信息" span><textarea name="notes" rows={5} defaultValue={editing==="new"?"":editing.notes}/></Field>
    </div><div className="modal-actions">{editing!=="new"&&<ConfirmButton confirmText="删除这份 Offer 详情？对应投递不会删除。" onConfirm={async()=>{await api(`/offers/${editing.id}`,{method:"DELETE"});setEditing(null);await refresh();}}><Trash2 size={14}/>删除详情</ConfirmButton>}<span className="action-spacer"/><button type="button" className="secondary-button" onClick={()=>setEditing(null)}>取消</button><button className="primary-button">保存详情</button></div></form></Modal>}
  </>;
}
