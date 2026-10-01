import { Field } from "./components";
import { normalizeIncome, type IncomeParameters } from "./incomePlans";
import type { TaxSettings } from "./offerTax";

export default function IncomeConditionsFields({ value, onChange, disabled = false, bonusControls = false }: {
  value: IncomeParameters; onChange: (value: IncomeParameters) => void; disabled?: boolean; bonusControls?: boolean;
}) {
  const p = normalizeIncome(value);
  const change = (part: Partial<IncomeParameters>) => onChange({ ...p, ...part });
  const tax = (part: Partial<TaxSettings>) => change({ tax: { ...p.tax, ...part } });
  const numberField = (key: "socialRate" | "fundRate" | "socialBase" | "fundBase" | "year" | "deduction" | "separateBonus", label: string, hint?: string) =>
    <Field label={label} hint={hint}><input type="number" min="0" max={key.endsWith("Rate") ? 100 : undefined} step={key === "year" ? 1 : .01} value={p.tax[key]} onChange={e => tax({ [key]: Number(e.target.value) })} /></Field>;
  return <fieldset className="income-conditions-fields" disabled={disabled}>
    <div className="income-input-grid">
      {numberField("socialRate", "个人社保合计比例（%）", "参考默认值 10.5%，请按公司实际条件修改")}
      {numberField("fundRate", "个人公积金比例（%）")}
      <Field label="单位公积金比例（%）" hint="仅用于账户入账，不增加到手现金"><input type="number" min="0" max="100" step="0.01" value={p.employerFundRate} onChange={e => change({ employerFundRate: Number(e.target.value) })} /></Field>
      <Field label="社保缴费基数"><select value={p.socialBaseMode} onChange={e => change({ socialBaseMode: e.target.value as "salary" | "custom", tax: { ...p.tax, socialBase: p.socialBaseMode === "salary" ? p.salary.monthlySalary : p.tax.socialBase } })}><option value="salary">按税前月薪</option><option value="custom">自定义基数</option></select></Field>
      <Field label="公积金缴费基数"><select value={p.fundBaseMode} onChange={e => change({ fundBaseMode: e.target.value as "salary" | "custom", tax: { ...p.tax, fundBase: p.fundBaseMode === "salary" ? p.salary.monthlySalary : p.tax.fundBase } })}><option value="salary">按税前月薪</option><option value="custom">自定义基数</option></select></Field>
      {p.socialBaseMode === "custom" && numberField("socialBase", "社保基数（元/月）")}
      {p.fundBaseMode === "custom" && numberField("fundBase", "公积金基数（元/月）")}
      <Field label="每天工作时长（小时）" hint="不含午休；仅用于时薪估算"><input type="number" min="0.01" max="24" step="0.01" value={p.hours || ""} onChange={e => change({ hours: Number(e.target.value) })} /></Field>
      <Field label="每周工作天数（天）"><input type="number" min="0.01" max="7" step="0.01" value={p.days || ""} onChange={e => change({ days: Number(e.target.value) })} /></Field>
    </div>
    <label className="offer-tax-toggle"><input type="checkbox" checked={p.confirmed === true} onChange={e => change({ confirmed: e.target.checked })} />已核对这个方案的缴费比例与基数</label>
    <p className="offer-tax-help">未核对时展示“默认／待核对估算”。基数不会自动限高保低；单位公积金按个人公积金的同一基数估算。</p>
    <details className="offer-tax-advanced"><summary>计算年份、扣除{bonusControls ? "与奖金计税" : ""}</summary>
      <div className="income-input-grid">{numberField("year", "计算年份")}{numberField("deduction", "专项附加扣除（元/月，可选）")}</div>
      {bonusControls && <>
        <label className="offer-tax-toggle"><input type="checkbox" checked={p.bonusEligible} onChange={e => change({ bonusEligible: e.target.checked, method: "combined" })} />有符合条件的全年一次性奖金</label>
        {p.bonusEligible && <div className="income-input-grid">{numberField("separateBonus", "符合条件的整笔年终奖（元）", "从额外薪数与奖金中划出，不增加总收入")}
          <Field label="展示使用的计税方式"><select value={p.method} onChange={e => change({ method: e.target.value as "combined" | "separate" })}><option value="combined">并入综合所得</option><option value="separate" disabled={p.tax.year > 2027}>全年一次性奖金单独计税</option></select></Field></div>}
      </>}
    </details>
  </fieldset>;
}
