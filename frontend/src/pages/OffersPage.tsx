import { useEffect, useMemo, useState } from "react";
import { BadgeDollarSign, CalendarClock, Pencil, Plus, Trash2, TrendingUp } from "lucide-react";
import { api, jsonBody, todayISO } from "../api";
import { ConfirmButton, EmptyState, Field, Modal, PageHeader, Panel } from "../components";
import type { PageProps } from "../App";
import type { Application, Offer } from "../types";
import "./offers.css";
import { estimateOffer } from "../offerTax";
import { emptyIncome, fromOffer, incomeConditions, incomeSummary } from "../incomePlans";
import IncomeConditionsFields from "../IncomeConditionsFields";
import { useUnsavedChanges } from "../navigationGuard";

const scoreFields = [
  ["growthScore", "成长空间"], ["interestScore", "业务兴趣"], ["locationScore", "地点满意"],
  ["stabilityScore", "稳定性"], ["workIntensity", "工作强度"],
] as const;
const decisions = ["考虑中", "倾向接受", "已接受", "已拒绝", "已过期"];
const invalidDecisionStatuses = new Set(["已拒绝", "已过期"]);
const pendingDecisionStatuses = new Set(["考虑中", "倾向接受"]);
const terminalApplicationStatuses = new Set(["终止", "已终止", "未通过", "主动放弃", "流程结束", "关闭", "已关闭", "暂不考虑"]);
const candidateStagePriority: Record<string, number> = {
  Offer: 0,
  "HR 面": 10,
  "业务面试": 20,
  "AI 面试": 30,
  笔试: 40,
  测评: 50,
  简历筛选: 60,
  已投递: 70,
  待投递: 80,
};
const numericFields = [
  "monthlySalary", "salaryMonths", "bonus", "signingBonus", "otherCompensation",
  "workIntensity", "growthScore", "interestScore", "locationScore", "stabilityScore",
] as const;

type Candidate = Pick<Application, "id" | "companyName" | "positionName" | "currentStatus" | "city">;
type EditorState = Offer | "new" | null;

const numericValue = (value: number | undefined | null) => (typeof value === "number" && Number.isFinite(value) ? value : 0);
const total = (offer: Offer) => numericValue(offer.monthlySalary) * numericValue(offer.salaryMonths) + numericValue(offer.bonus) + numericValue(offer.signingBonus) + numericValue(offer.otherCompensation);
const recurringTotal = (offer: Offer) => total(offer) - numericValue(offer.signingBonus);
const scoreValue = (value: number | undefined | null) => Math.min(5, Math.max(1, numericValue(value) || 3));
const score = (offer: Offer) => Math.round(((scoreValue(offer.growthScore) + scoreValue(offer.interestScore) + scoreValue(offer.locationScore) + scoreValue(offer.stabilityScore) + (6 - scoreValue(offer.workIntensity))) / 25) * 100);
const money = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return "待填写";
  return `¥${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
};
const isTerminalApplication = (application: Pick<Application, "currentStatus">) => terminalApplicationStatuses.has(application.currentStatus.trim());
const candidateRank = (application: Candidate) => candidateStagePriority[application.currentStatus] ?? (isTerminalApplication(application) ? 1000 : 500);
const isOfferInvalid = (offer: Offer) => invalidDecisionStatuses.has(offer.decisionStatus);

function candidateText(application: Candidate) {
  return `${application.companyName} ${application.positionName} ${application.currentStatus} ${application.city}`.toLocaleLowerCase("zh-CN");
}

function candidateLabel(application: Candidate) {
  return `${application.companyName} · ${application.positionName}（${application.currentStatus || "未设置"}）`;
}

export default function OffersPage({ data, refresh, go }: PageProps) {
  const [editing, setEditing] = useState<EditorState>(null);
  const [candidateSearch, setCandidateSearch] = useState("");
  const [includeTerminated, setIncludeTerminated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [conditions, setConditions] = useState(emptyIncome);
  const [dirty, setDirty] = useState(false);
  const [sortBy, setSortBy] = useState("gross");
  const [expanded, setExpanded] = useState<number | null>(null);
  useUnsavedChanges(dirty, saving || deleting);
  const today = todayISO();

  // The global shell has a desktop minimum width. This page opts into a compact
  // layout so an 800px desktop window can still scroll the comparison table.
  useEffect(() => {
    document.body.classList.add("offers-page-active");
    return () => document.body.classList.remove("offers-page-active");
  }, []);

  // Modal owns the only scrollable surface while editing. The shared Modal
  // component owns the body scroll lock; this class is only for page styling.
  useEffect(() => {
    if (!editing) return undefined;
    document.body.classList.add("offers-modal-open");
    return () => {
      document.body.classList.remove("offers-modal-open");
    };
  }, [editing]);

  useEffect(() => {
    setCandidateSearch("");
    setIncludeTerminated(false);
    setDeleting(false);
    setConditions(fromOffer(editing && editing !== "new" ? editing : undefined));
    setDirty(false);
  }, [editing]);

  const existingOfferIds = useMemo(() => new Set(data.offers.map((offer) => offer.applicationId)), [data.offers]);
  const estimates = useMemo(() => new Map(data.offers.map(offer => { const p = fromOffer(offer); return [offer.id, { p, ...incomeSummary(p) }]; })), [data.offers]);
  const sorted = useMemo(() => [...data.offers].sort((a, b) => {
    const metric = (offer: Offer) => { const e = estimates.get(offer.id)!; if (sortBy === "net") return e.result.error ? -1 : e.result.net; if (sortBy === "fund") return e.fund.error ? -1 : e.fund.monthly; if (sortBy === "hourly") return e.hourly ?? -1; return total(offer); };
    return Number(isOfferInvalid(a)) - Number(isOfferInvalid(b)) || metric(b) - metric(a);
  }), [data.offers, estimates, sortBy]);
  const validOffers = useMemo(() => data.offers.filter((offer) => !isOfferInvalid(offer)), [data.offers]);
  const confirmedNets = validOffers.flatMap(offer => { const e = estimates.get(offer.id)!; return e.p.confirmed && !e.result.error ? [e.result.net] : []; });
  const highestValidTotal = confirmedNets.length ? Math.max(...confirmedNets) : null;
  const nearestDeadline = useMemo(() => data.offers
    .filter((offer) => offer.deadline && offer.deadline >= today && pendingDecisionStatuses.has(offer.decisionStatus))
    .map((offer) => offer.deadline)
    .sort()[0] || "", [data.offers, today]);

  const newEligibleCandidates = useMemo(() => data.applications.filter((application) => !existingOfferIds.has(application.id) && !isTerminalApplication(application)), [data.applications, existingOfferIds]);
  const hiddenTerminalCandidates = useMemo(() => data.applications.filter((application) => !existingOfferIds.has(application.id) && isTerminalApplication(application)), [data.applications, existingOfferIds]);
  const canAddOffer = newEligibleCandidates.length > 0 || hiddenTerminalCandidates.length > 0;
  const editingApplicationId = editing && editing !== "new" ? editing.applicationId : null;

  const candidates = useMemo<Candidate[]>(() => {
    const available = data.applications
      .filter((application) => {
        const isCurrent = editingApplicationId === application.id;
        if (isCurrent) return true;
        if (existingOfferIds.has(application.id)) return false;
        return includeTerminated || !isTerminalApplication(application);
      })
      .map(({ id, companyName, positionName, currentStatus, city }) => ({ id, companyName, positionName, currentStatus, city }));

    // Keep an editable record visible even if its application was archived or
    // removed from the current application list.
    if (editing && editing !== "new" && !available.some((application) => application.id === editing.applicationId)) {
      available.push({
        id: editing.applicationId,
        companyName: editing.companyName,
        positionName: editing.positionName,
        currentStatus: "当前 Offer",
        city: editing.location,
      });
    }

    return available.sort((a, b) => candidateRank(a) - candidateRank(b) || a.companyName.localeCompare(b.companyName, "zh-CN") || a.positionName.localeCompare(b.positionName, "zh-CN"));
  }, [data.applications, editing, editingApplicationId, existingOfferIds, includeTerminated]);

  const visibleCandidates = useMemo(() => {
    const query = candidateSearch.trim().toLocaleLowerCase("zh-CN");
    const filtered = query ? candidates.filter((candidate) => candidateText(candidate).includes(query)) : candidates;
    if (editingApplicationId && !filtered.some((candidate) => candidate.id === editingApplicationId)) {
      const current = candidates.find((candidate) => candidate.id === editingApplicationId);
      return current ? [current, ...filtered] : filtered;
    }
    return filtered;
  }, [candidateSearch, candidates, editingApplicationId]);

  const closeEditor = () => {
    if (!saving && !deleting && (!dirty || window.confirm("Offer 有未保存的修改，确定放弃吗？"))) { setDirty(false); setEditing(null); }
  };

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || deleting) return;
    const values = Object.fromEntries(new FormData(event.currentTarget).entries()) as Record<string, string>;
    const applicationId = Number(values.applicationId);
    if (!Number.isInteger(applicationId) || applicationId < 1) {
      window.alert("请选择对应岗位。");
      return;
    }

    const duplicate = data.offers.find((offer) => offer.applicationId === applicationId && (editing === "new" || offer.id !== editing?.id));
    if (duplicate) {
      window.alert("该岗位已经有一份 Offer 详情，未保存本次修改，以避免覆盖原记录。");
      return;
    }

    const payload: Record<string, string | number | boolean> = { ...values, applicationId, createOnly: editing === "new" };
    numericFields.forEach((key) => {
      const raw = values[key]?.trim() ?? "";
      payload[key] = raw === "" ? 0 : Number(raw);
    });
    // Preserve historical calculator settings when editing Offer facts.
    payload.taxSettings = editing && editing !== "new" ? editing.taxSettings || "" : "";
    payload.incomeSettings = JSON.stringify(incomeConditions(conditions));
    payload.expectedUpdatedAt = editing && editing !== "new" ? editing.updatedAt : "";

    setSaving(true);
    try {
      await api("/offers", { method: "PUT", ...jsonBody(payload) });
      setDirty(false);
      setEditing(null);
      await refresh();
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "Offer 保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteOffer(offer: Offer) {
    if (saving || deleting) return;
    setDeleting(true);
    try {
      await api(`/offers/${offer.id}`, { method: "DELETE" });
      setEditing(null);
      await refresh();
    } catch (reason) {
      window.alert(reason instanceof Error ? reason.message : "Offer 删除失败");
    } finally {
      setDeleting(false);
    }
  }

  const editorOffer = editing && editing !== "new" ? editing : null;
  const editorHasCandidates = editing === "new" ? visibleCandidates.length > 0 : Boolean(editorOffer);

  return (
    <div className="offers-page">
      <PageHeader
        title="Offer 对比"
        description="把薪酬、成长、地点和风险放到同一把尺子上，记录事实，不替你做决定。"
        action={<button className="primary-button" disabled={!canAddOffer} title={canAddOffer ? "为尚未关联 Offer 的岗位补充信息" : "没有可新增 Offer 的岗位"} onClick={() => setEditing("new")}><Plus size={16} />添加 Offer 详情</button>}
      />

      <section className="offer-summary-grid" aria-label="Offer 概览">
        <article><BadgeDollarSign /><span>已记录 Offer</span><strong>{data.offers.length}</strong></article>
        <article><TrendingUp /><span>最高完整年度到手 · 已核对条件</span><strong title="含一次性现金；仅统计缴费条件已核对且未拒绝、未过期的 Offer">{highestValidTotal === null ? "请先核对缴费条件" : money(highestValidTotal)}</strong></article>
        <article><CalendarClock /><span>最近决策截止 · 有效 Offer</span><strong>{nearestDeadline || "无近期截止"}</strong></article>
      </section>

      <Panel title="横向比较" description="统一按完整工作 12 个月估算，含一次性现金；月均含奖金摊平，不是每月工资条。公积金入账不算到手现金。奖金请勿重复填写。">
        <div className="offer-comparison-toolbar"><span>默认／待核对结果仅作参考，不代表公司承诺。</span><label>排序 <select aria-label="Offer 排序" value={sortBy} onChange={e => setSortBy(e.target.value)}><option value="gross">全年税前</option><option value="net">预计全年到手</option><option value="fund">公积金月入账</option><option value="hourly">税后时薪</option></select></label></div>
        {sorted.length ? <div className="offer-table-wrap" role="region" aria-label="Offer 横向比较表" tabIndex={0}>
          <table className="offer-table"><thead><tr><th>公司 / 岗位</th><th>税前薪资</th><th>预计全年到手</th><th>月均到手</th><th>公积金入账</th><th>决策 / 截止</th><th>操作</th></tr></thead>
            {sorted.map((offer) => {
              const invalid = isOfferInvalid(offer);
              const e = estimates.get(offer.id)!;
              const ordinary = estimateOffer({ ...e.p.salary, salaryMonths: 12, bonus: 0, signingBonus: 0, otherCompensation: 0 }, { ...e.tax, separateBonus: 0 });
              const recurring = estimateOffer({ ...e.p.salary, signingBonus: 0 }, e.tax);
              return <tbody key={offer.id}><tr className={invalid ? "offer-row-inactive" : undefined}>
                <td><strong>{offer.companyName}</strong><small>{offer.positionName}</small><small>{offer.location || "地点待填写"}</small></td>
                <td className="offer-total"><span>{money(offer.monthlySalary)} × {offer.salaryMonths}</span><small>全年税前 {money(total(offer))}</small></td>
                <td className="offer-net"><strong>{e.result.error ? "待补充条件" : money(e.result.net)}</strong><small className={e.p.confirmed ? "estimate-confirmed" : "estimate-default"}>{e.p.confirmed ? "缴费条件已核对" : "默认／待核对估算"}</small><small>{e.tax.year} · {e.p.method === "separate" && e.p.bonusEligible ? "奖金单独计税" : "并入综合所得"}</small></td>
                <td><strong>{e.result.error ? "—" : money(e.result.average)}</strong><small>含奖金摊平</small><small>基本工资月均 {ordinary.error ? "—" : money(ordinary.average)}</small></td>
                <td><strong>{e.fund.error ? "待检查" : `${money(e.fund.monthly)}/月`}</strong><small>个人 {e.p.tax.fundRate}% / 单位 {e.p.employerFundRate}%</small></td>
                <td><span className={`decision-badge decision-${offer.decisionStatus}`}>{offer.decisionStatus || "未设置"}</span><small>{offer.deadline || "无截止日期"}</small>{invalid && <small>不计入概览</small>}</td>
                <td><div className="offer-row-actions"><button className="row-toggle" onClick={() => setEditing(offer)}><Pencil size={14} />编辑</button><button className="row-toggle" onClick={() => go(`income?offer=${offer.id}`)}>收入计算</button><button className="text-button" aria-expanded={expanded === offer.id} onClick={() => setExpanded(expanded === offer.id ? null : offer.id)}>更多详情</button></div></td>
              </tr>{expanded === offer.id && <tr className="offer-comparison-detail"><td colSpan={7}><div><span>税后时薪：{e.hourly == null ? "工时待补充" : `${money(e.hourly)}/小时`}</span><span>常规年度到手（不含签字费）：{recurring.error ? "—" : money(recurring.net)}</span><span>常规年度税前：{money(recurringTotal(offer))}</span><span>综合参考评分：{score(offer)}</span><span>{e.result.error || `社保基数 ${money(e.tax.socialBase)} / 公积金基数 ${money(e.tax.fundBase)}`}</span><span>{offer.notes || "暂无补充说明"}</span></div></td></tr>}</tbody>;
            })}
          </table>
        </div> : <EmptyState title="还没有 Offer 详情" description="收到口头或正式 Offer 后即可关联投递记录。新增时默认隐藏终止岗位，并且不会覆盖已有 Offer。" action={canAddOffer ? <button className="secondary-button" onClick={() => setEditing("new")}>添加第一份 Offer</button> : undefined} />}
      </Panel>

      {editing && <Modal title={editing === "new" ? "添加 Offer 详情" : "编辑 Offer 详情"} subtitle="金额均为税前人民币；不确定的项目可以留空。" onClose={closeEditor} wide>
        <form className="offers-modal-form" onSubmit={save} onChange={event => { setDirty(true); const values = new FormData(event.currentTarget); setConditions(p => ({ ...p, salary: { monthlySalary: Number(values.get("monthlySalary")), salaryMonths: Number(values.get("salaryMonths")) || 12, bonus: Number(values.get("bonus")), signingBonus: Number(values.get("signingBonus")), otherCompensation: Number(values.get("otherCompensation")) } })); }}>
          <fieldset className="modal-form-grid" disabled={saving || deleting}>
            <div className="field field-span offer-application-field">
              <span>对应岗位</span>
              <div className="offer-application-tools">
                <input aria-label="搜索岗位" value={candidateSearch} onChange={(event) => setCandidateSearch(event.target.value)} placeholder="搜索公司、岗位或阶段" autoComplete="off" />
                {hiddenTerminalCandidates.length > 0 && <label className="offer-terminal-toggle"><input type="checkbox" checked={includeTerminated} onChange={(event) => setIncludeTerminated(event.target.checked)} />显示终止岗位（{hiddenTerminalCandidates.length}）</label>}
              </div>
              {editing === "new" ? <select name="applicationId" required defaultValue="" disabled={!editorHasCandidates || saving} onChange={event => { const candidate = candidates.find(c => c.id === Number(event.target.value)); const location = event.currentTarget.form?.elements.namedItem("location") as HTMLInputElement | null; if (location && !location.value && candidate?.city) location.value = candidate.city; }}>
                <option value="" disabled>{editorHasCandidates ? "选择对应投递" : "没有符合条件的岗位"}</option>
                {visibleCandidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidateLabel(candidate)}</option>)}
              </select> : <>
                <select name="applicationIdDisplay" defaultValue={editorOffer?.applicationId} disabled aria-describedby="offer-application-help">
                  {visibleCandidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidateLabel(candidate)}</option>)}
                </select>
                <input type="hidden" name="applicationId" value={editorOffer?.applicationId ?? ""} />
              </>}
              <small id="offer-application-help">{editing === "new" ? "优先显示 Offer、业务面试和 HR 面阶段；已有 Offer 的岗位不会出现在新增列表。" : "此 Offer 关联当前岗位；薪资、福利和决策信息均可修改。"}</small>
            </div>
            <Field label="部门 / 业务"><input name="department" defaultValue={editing === "new" ? "" : editing.department} /></Field>
            <Field label="工作地点"><input name="location" defaultValue={editing === "new" ? "" : editing.location} /></Field>
            <Field label="税前月薪（元/月）" hint="例如 15000 表示 1.5 万元/月"><input name="monthlySalary" type="number" min="0" step="0.01" defaultValue={editing === "new" ? "" : editing.monthlySalary ?? ""} /></Field>
            <Field label="薪资月数" hint="留空按 12 薪；额外薪数不要再重复填入年度奖金。"><input name="salaryMonths" type="number" min="1" step="0.5" defaultValue={editing === "new" ? 12 : editing.salaryMonths ?? ""} /></Field>
            <Field label="额外年度奖金（元/年）" hint="不重复计入薪资月数已包含的奖金；浮动条件请记录到备注。"><input name="bonus" type="number" min="0" step="0.01" defaultValue={editing === "new" ? "" : editing.bonus ?? ""} /></Field>
            <Field label="签字费（元，一次性）"><input name="signingBonus" type="number" min="0" step="0.01" defaultValue={editing === "new" ? "" : editing.signingBonus ?? ""} /></Field>
            <Field label="其他现金（元/年）" hint="仅填写按工资计税的现金；股权、报销等请另记备注"><input name="otherCompensation" type="number" min="0" step="0.01" defaultValue={editing === "new" ? "" : editing.otherCompensation ?? ""} /></Field>
            <Field label="接受截止日期"><input name="deadline" type="date" defaultValue={editing === "new" ? "" : editing.deadline} /></Field>
            <details className="field-span offer-conditions-section"><summary>社保、公积金与工作条件 <small>{conditions.confirmed ? "已核对" : "默认／待核对"}</small></summary><IncomeConditionsFields value={conditions} disabled={saving || deleting} bonusControls onChange={value => { setConditions(value); setDirty(true); }} /></details>
            <details className="field-span offer-conditions-section"><summary>主观评分（可选）</summary><div className="income-input-grid">{scoreFields.map(([key, label]) => <Field label={`${label}（1–5）`} key={key}><select name={key} defaultValue={editing === "new" ? 3 : editing[key]}>{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}</option>)}</select></Field>)}</div></details>
            <Field label="决策状态"><select name="decisionStatus" defaultValue={editing === "new" ? "考虑中" : editing.decisionStatus}>{decisions.map((value) => <option key={value}>{value}</option>)}</select></Field>
            <Field label="风险、福利与补充信息" span><textarea name="notes" rows={5} defaultValue={editing === "new" ? "" : editing.notes} /></Field>
          </fieldset>
          <div className="modal-actions offers-modal-actions">
            {editing !== "new" && <ConfirmButton confirmText="删除这份 Offer 详情？对应投递不会删除。" onConfirm={() => deleteOffer(editing)}>{deleting ? "删除中…" : <><Trash2 size={14} />删除详情</>}</ConfirmButton>}
            <span className="action-spacer" /><button type="button" className="secondary-button" onClick={closeEditor} disabled={saving || deleting}>取消</button><button className="primary-button" disabled={saving || deleting || !editorHasCandidates}>{saving ? "保存中…" : "保存详情"}</button>
          </div>
        </form>
      </Modal>}
    </div>
  );
}
