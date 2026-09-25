import { useEffect, useState } from "react";
import type { PageProps } from "../App";
import type { Offer } from "../types";
import { api, jsonBody } from "../api";
import { Field, PageHeader, Panel } from "../components";
import { estimateOffer, compareBonusTax, housingFund, readTaxSettings, type SalaryInput, type TaxSettings } from "../offerTax";
import { emptyIncome, type IncomeParameters, type IncomePlan } from "../incomePlans";
import "./offers.css";

const money = (n: number) => `¥${n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
function fromOffer(offer?: Offer): IncomeParameters {
  const p = emptyIncome();
  if (!offer) return p;
  p.salary = { monthlySalary: offer.monthlySalary || 0, salaryMonths: offer.salaryMonths || 12, bonus: offer.bonus || 0, signingBonus: offer.signingBonus || 0, otherCompensation: offer.otherCompensation || 0 };
  if (offer.taxSettings) { p.tax = readTaxSettings(offer.taxSettings); p.customBases = true; }
  return p;
}
export default function IncomePage({ data, go }: PageProps) {
  const requested = new URLSearchParams(window.location.hash.split("?")[1] || "").get("offer") || "";
  const [offerID, setOfferID] = useState(requested);
  const [p, setP] = useState(() => fromOffer(data.offers.find(o => String(o.id) === requested)));
  const [plans, setPlans] = useState<IncomePlan[]>([]);
  const [planID, setPlanID] = useState(0);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  useEffect(() => { let active = true; api<IncomePlan[]>("/income-plans").then(items => { if (active) setPlans(items); }).catch(e => { if (active) setMessage(`读取方案失败：${e.message}`); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  const change = (values: Partial<IncomeParameters>) => { setP(prev => ({ ...prev, ...values })); setDirty(true); setMessage(""); };
  const changeTax = (values: Partial<TaxSettings>) => change({ tax: { ...p.tax, ...values } });
  const canReplace = () => !dirty || window.confirm("当前修改尚未保存，确定切换吗？");
  const tax = { ...p.tax, enabled: true, socialBase: p.customBases ? p.tax.socialBase : p.salary.monthlySalary, fundBase: p.customBases ? p.tax.fundBase : p.salary.monthlySalary };
  const comparison = p.bonusEligible && tax.separateBonus > 0 ? compareBonusTax(p.salary, tax) : null;
  const selectedTax = { ...tax, separateBonus: p.bonusEligible && p.method === "separate" ? tax.separateBonus : 0 };
  const result = estimateOffer(p.salary, selectedTax);
  const recurring = estimateOffer({ ...p.salary, signingBonus: 0 }, selectedTax);
  const ordinary = estimateOffer({ ...p.salary, salaryMonths: 12, bonus: 0, signingBonus: 0, otherCompensation: 0 }, { ...tax, separateBonus: 0 });
  const fund = housingFund(tax.fundBase, tax.fundRate, p.employerFundRate);
  const validHours = Number.isFinite(p.hours) && p.hours > 0 && p.hours <= 24 && Number.isFinite(p.days) && p.days > 0 && p.days <= 7;
  const error = result.error || fund.error || (p.bonusEligible && tax.separateBonus <= 0 ? "请填写符合条件的整笔全年一次性奖金金额。" : comparison?.error) || (!validHours ? "请填写有效工时：每天大于 0 且不超过 24 小时，每周大于 0 且不超过 7 天。" : "");
  async function save(copy = false) {
    if (busy || loading) return;
    if (error || !name.trim()) { setMessage(error || "请给薪资方案起个名字。"); return; }
    setBusy(true);
    try {
      const saved = await api<{ id: number }>("/income-plans", { method: "PUT", ...jsonBody({ id: copy ? 0 : planID, name: name.trim(), parameters: p }) });
      setPlanID(saved.id); setDirty(false); setMessage("方案已保存到本地数据库，随数据库备份。结果按保存的参数重新计算。");
      setPlans(await api<IncomePlan[]>("/income-plans"));
    } catch (e) { setMessage(e instanceof Error ? e.message : "保存失败，请重试"); } finally { setBusy(false); }
  }
  async function remove() {
    if (!planID || busy || !window.confirm("删除这个已保存方案？不会影响 Offer 和投递。")) return;
    setBusy(true);
    try { await api(`/income-plans/${planID}`, { method: "DELETE" }); setPlans(items => items.filter(x => x.id !== planID)); setPlanID(0); setDirty(true); setMessage("已删除保存记录，当前试算仍保留，可另存。"); }
    catch (e) { setMessage(e instanceof Error ? e.message : "删除失败"); } finally { setBusy(false); }
  }
  const salaryField = (key: keyof SalaryInput, label: string, hint?: string) => <Field label={label} hint={hint}><input type="number" min={key === "salaryMonths" ? 12 : 0} step="0.01" value={p.salary[key] || ""} placeholder="0" onChange={e => change({ salary: { ...p.salary, [key]: Number(e.target.value) } })} /></Field>;
  const taxField = (key: keyof Omit<TaxSettings, "enabled">, label: string, hint?: string) => <Field label={label} hint={hint}><input type="number" min="0" max={key.endsWith("Rate") ? 100 : undefined} step={key === "year" ? 1 : .01} value={p.tax[key]} onChange={e => changeTax({ [key]: Number(e.target.value) })} /></Field>;
  return <div className="income-page">
    <PageHeader title="收入计算" description="薪资、税费与公积金，一份清晰的收入说明。计算不会改写 Offer。" action={<button className="secondary-button" onClick={() => { if (canReplace()) go("offers"); }}>返回 Offer</button>} />
    <Panel title="我的薪资方案" description="保存多种方案，便于重复测算；只保存在本机，不联网传输薪资。">
      <div className="income-plan-toolbar">
        <Field label="已保存方案"><select disabled={busy || loading} value={planID} onChange={e => { if (!canReplace()) return; const id = Number(e.target.value); const item = plans.find(x => x.id === id); setPlanID(id); setP(item ? structuredClone(item.parameters) : emptyIncome()); setName(item?.name || ""); setOfferID(""); setDirty(false); setMessage(""); }}><option value="0">{loading ? "读取中…" : "新建试算"}</option>{plans.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        <Field label="方案名称"><input maxLength={80} value={name} placeholder="例如 上海研发 · 15k × 13" onChange={e => { setName(e.target.value); setDirty(true); }} /></Field>
        <div className="income-plan-actions"><button className="primary-button" disabled={busy || loading} onClick={() => void save()}>{busy ? "处理中…" : planID ? "保存修改" : "保存方案"}</button>{planID > 0 && <><button className="secondary-button" disabled={busy} onClick={() => void save(true)}>另存一份</button><button className="secondary-button" disabled={busy} onClick={() => void remove()}>删除方案</button></>}</div>
      </div>
      <p className="income-save-status" role="status">{message || (dirty ? "有未保存修改；离开页面前请保存。" : planID ? "已载入保存的参数，可直接修改并重新计算。" : "未保存的试算在离开或刷新后重置。")}</p>
    </Panel>
    <Panel title="计算条件" description="金额统一为人民币元，不是 k；按同一单位完整工作 12 个月估算。">
      <Field label="从 Offer 带入（可选）"><select value={offerID} disabled={busy} onChange={e => { if (!canReplace()) return; const id = e.target.value; const offer = data.offers.find(o => String(o.id) === id); setOfferID(id); setP(fromOffer(offer)); setPlanID(0); setName(offer ? `${offer.companyName} · ${offer.positionName}` : ""); setDirty(Boolean(offer)); setMessage(""); }}><option value="">独立试算，不关联 Offer</option>{data.offers.map(o => <option key={o.id} value={o.id}>{o.companyName} · {o.positionName}</option>)}</select></Field>
      <div className="income-input-grid">
        {salaryField("monthlySalary", "税前月薪（元/月）", "15000 表示 1.5 万元/月")}
        {salaryField("salaryMonths", "薪资月数（薪/年）", "额外薪数已包含的奖金不要重复填写")}
        {salaryField("bonus", "额外奖金（元/年）")}
        {salaryField("signingBonus", "签字费（元，一次性）")}
        {salaryField("otherCompensation", "其他现金收入（元/年）")}
        {taxField("socialRate", "个人社保合计比例（%）", "默认上海参考值 10.5%：养老 8%＋医疗 2%＋失业 0.5%，可修改")}
        {taxField("fundRate", "个人公积金比例（%）", "默认 5%，按实际缴存比例修改")}
        <Field label="单位公积金比例（%）" hint="默认 5%，仅用于账户入账估算"><input type="number" min="0" max="100" step="0.01" value={p.employerFundRate} onChange={e => change({ employerFundRate: Number(e.target.value) })} /></Field>
        <Field label="每天工作时长（小时）" hint="填写实际工作时间，不含午休"><input type="number" min="0.1" max="24" step="0.5" value={p.hours || ""} onChange={e => change({ hours: Number(e.target.value) })} /></Field>
        <Field label="每周工作天数（天）"><input type="number" min="0.1" max="7" step="0.5" value={p.days || ""} onChange={e => change({ days: Number(e.target.value) })} /></Field>
      </div>
      <details className="offer-tax-advanced"><summary>缴费基数与可选扣除</summary>
        <label className="offer-tax-toggle"><input type="checkbox" checked={p.customBases} onChange={e => change({ customBases: e.target.checked, tax: e.target.checked ? { ...p.tax, socialBase: tax.socialBase, fundBase: tax.fundBase } : p.tax })} />自定义缴费基数（默认按月薪，不自动限高保低）</label>
        <div className="income-input-grid">{p.customBases && <>{taxField("socialBase", "社保基数（元/月）")}{taxField("fundBase", "公积金基数（元/月）")}</>}{taxField("year", "计算年份")}{taxField("deduction", "专项附加扣除（元/月，可选）", "默认 0；符合条件时填写，否则低收入情形的税额比较可能不同")}</div>
      </details>
    </Panel>
    <Panel title="年终奖计税对比" description="比较同一笔符合条件的全年一次性奖金，不拆分奖金，不把整个年包当年终奖。">
      <label className="offer-tax-toggle"><input type="checkbox" checked={p.bonusEligible} onChange={e => change({ bonusEligible: e.target.checked, method: "combined" })} />我有符合条件的全年一次性奖金，需要比较两种计税方式</label>
      {p.bonusEligible ? <>
        <div className="income-input-grid">{taxField("separateBonus", "符合条件的整笔年终奖（元）", "从额外薪数与年度奖金合计中划出，不增加总收入；请填整笔，不任意拆分。单独计税一个纳税年度只能使用一次。")}</div>
        {comparison && "recommended" in comparison ? <>
          <div className="income-tax-choices">{([['combined', '并入综合所得', comparison.combined], ['separate', '单独计税', comparison.separate]] as const).map(([key, label, value]) => <button type="button" className={`income-tax-choice ${p.method === key ? "selected" : ""}`} aria-pressed={p.method === key} key={key} onClick={() => change({ method: key })}><span>{label}{comparison.recommended === key && <b>当前条件下更省税</b>}</span><strong>全年个税 {money(value.tax)}</strong><small>全年到手 {money(value.net)} · 月均 {money(value.average)}</small></button>)}</div>
          <p className="income-recommendation">{comparison.recommended === "equal" ? "两种方式预计税额相同。" : `当前输入下，${comparison.recommended === "separate" ? "单独计税" : "并入综合所得"}预计少缴 ${money(comparison.saving)}。`}下方展示你选中的方式；此结论不是申报资格认定。</p>
        </> : <p role="status" className="offer-tax-error">{comparison?.error || "填写奖金金额后显示对比。"}</p>}
      </> : <p className="offer-tax-help">当前所有奖金并入综合所得估算。仅在满足条件时开启对比；现行单独计税政策配置至 2027 年底。</p>}
    </Panel>
    <Panel title="预计收入" description={`当前口径：${p.bonusEligible && p.method === "separate" ? "年终奖单独计税" : "全部并入综合所得"} · ${tax.year} 年 · 月均是全年摊平，不代表每月实际到账。`}>
      {error ? <p role="status" className="offer-tax-error">{error}</p> : !result.error && !fund.error && <>
        <div className="income-results" aria-live="polite">
          <article><span>全年税前现金</span><strong>{money(result.gross)}</strong><small>含额外薪数、奖金与首年签字费</small></article>
          <article className="income-result-primary"><span>首年全年到手</span><strong>{money(result.net)}</strong><small>常规年（不含签字费）{recurring.error ? "—" : money(recurring.net)}</small></article>
          <article><span>月均到手 · 含奖金摊平</span><strong>{money(result.average)}</strong><small>基本工资单独估算月均 {ordinary.error ? "—" : money(ordinary.average)}</small></article>
          <article><span>含奖金首年税后时薪</span><strong>{money(result.net / (p.hours * p.days * 52))}<em>/小时</em></strong><small>基本工资税后时薪 {ordinary.error ? "—" : money(ordinary.net / (p.hours * p.days * 52))}；按每年 52 周，不扣假期</small></article>
        </div>
        <div className="income-deductions" aria-label="全年扣款明细"><div><span>个人社保 / 年</span><strong>{money(result.social)}</strong></div><div><span>个人公积金 / 年</span><strong>{money(result.fund)}</strong></div><div><span>个人所得税 / 年</span><strong>{money(result.tax)}</strong></div></div>
        <section className="income-fund" aria-label="公积金账户入账"><div><h3>公积金账户预计新增</h3><p>个人 {money(fund.personal)} ＋ 单位 {money(fund.employer)} / 月</p></div><div><strong>{money(fund.monthly)}<small> / 月</small></strong><span>{money(fund.monthly)} × 12 = {money(fund.annual)} / 年</span></div><p>不是账户当前余额，不计入上面的到手现金；不含利息、提取与补充公积金，单位部分假设采用同一基数。</p></section>
        <details className="income-months"><summary>查看每月到手明细{comparison && "recommended" in comparison ? " · 两种计税方式对照" : ""}</summary><div className="offer-tax-table"><table><thead><tr><th>月份</th><th>税前现金</th><th>个人缴费</th>{comparison && "recommended" in comparison ? <><th>并入后到手</th><th>单独计税后到手</th></> : <><th>个税</th><th>到手现金</th></>}</tr></thead><tbody>{result.months.map((m, i) => <tr key={m.month}><td>{m.month} 月</td><td>{money(m.gross)}</td><td>{money(m.contributions)}</td>{comparison && "recommended" in comparison ? <><td>{money(comparison.combined.months[i].net)}</td><td>{money(comparison.separate.months[i].net)}</td></> : <><td>{money(m.tax)}</td><td>{money(m.net)}</td></>}</tr>)}</tbody></table></div></details>
      </>}
      <p className="offer-tax-help">按中国大陆居民个人、同一单位完整工作 12 个月的累计预扣法估算。奖金与其他额外现金假设 12 月发放，不含其他收入、减免税、单位超标准缴存税务影响或年度汇算调整。个人缴费假设均可税前扣除，缴费上下限及资格请自行确认。月度分配、舍入以工资条和税务核算为准。</p>
      <p className="income-sources"><a href="https://www.shanghai.gov.cn/nw17239/20251211/6a00e933de0347acbc172518d6bbab79.html" target="_blank" rel="noreferrer">上海个人缴费比例参考</a><a href="https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211524/content.html" target="_blank" rel="noreferrer">年终奖计税政策</a><span>算法口径：2026-09 核对</span></p>
    </Panel>
  </div>;
}
