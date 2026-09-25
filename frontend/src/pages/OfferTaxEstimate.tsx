import { useState } from "react";
import { Field } from "../components";
import { estimateOffer, readTaxSettings, type SalaryInput, type TaxSettings } from "../offerTax";

const yuan = (n: number) => `¥${n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export default function OfferTaxEstimate({ salary, initial }: { salary: SalaryInput; initial?: string }) {
  const [tax, setTax] = useState(() => readTaxSettings(initial));
  const result = estimateOffer(salary, tax);
  const input = (key: keyof Omit<TaxSettings, "enabled">, label: string, hint?: string) => <Field label={label} hint={hint}><input type="number" min="0" max={key.endsWith("Rate") ? 100 : undefined} step={key === "year" ? 1 : .01} value={tax[key] || ""} placeholder="0" onChange={e => setTax({ ...tax, [key]: e.target.value === "" ? 0 : Number(e.target.value) })} /></Field>;
  return <section className="offer-tax field-span" aria-label="预计到手计算">
    <input type="hidden" name="taxSettings" value={JSON.stringify(tax)} />
    <label className="offer-tax-toggle"><input type="checkbox" checked={tax.enabled} onChange={e => setTax({ ...tax, enabled: e.target.checked })} /><span><strong>预计到手</strong><small>可选 · 本地计算 · 自填缴费比例，不查询城市政策</small></span></label>
    {tax.enabled && <>
      <p className="offer-tax-help">按居民个人、全年在同一单位工作 12 个月估算。请填写公司实际采用的个人缴费比例与基数；默认 0 仅表示未计入，不代表免缴。基数上限、税前扣除资格需自行确认。</p>
      <div className="offer-tax-inputs">
        {input("socialBase", "社保缴费基数（元/月）")}{input("socialRate", "个人社保合计比例（%）", "养老、医疗、失业等个人部分合计，不含单位部分")}
        {input("fundBase", "公积金缴费基数（元/月）")}{input("fundRate", "个人公积金比例（%）")}
      </div>
      <details className="offer-tax-advanced"><summary>扣除与奖金计税设置</summary><div className="offer-tax-inputs">
        {input("deduction", "专项附加扣除（元/月）", "符合条件的租房、赡养老人等扣除合计，不是现金支出")}
        {input("year", "计算年份")}
        {input("separateBonus", "其中：单独计税年终奖（元）", "从额外薪数及年度奖金中划出，不额外增加收入；默认全部并入综合所得。仅适用于符合条件的全年一次性奖金。")}
      </div></details>
      {result.error ? <p className="offer-tax-error" role="status">{result.error}</p> : <>
        <div className="offer-tax-results" aria-live="polite"><div><span>预计全年到手</span><strong>{yuan(result.net)}</strong></div><div><span>月均到手（含奖金摊平）</span><strong>{yuan(result.average)}</strong></div></div>
        <p className="offer-tax-help">全年个税 {yuan(result.tax)} · 个人社保 {yuan(result.social)} · 个人公积金 {yuan(result.fund)}。公积金不计入到手现金，未估算单位缴存部分。</p>
        <details><summary>查看 12 个月估算明细</summary><div className="offer-tax-table"><table><thead><tr><th>月份</th><th>税前现金</th><th>个人缴费</th><th>个税</th><th>到手现金</th></tr></thead><tbody>{result.months.map(m => <tr key={m.month}><td>{m.month} 月</td><td>{yuan(m.gross)}</td><td>{yuan(m.contributions)}</td><td>{yuan(m.tax)}</td><td>{yuan(m.net)}</td></tr>)}</tbody></table></div></details>
      </>}
      <p className="offer-tax-help">比较口径：每月发放基本月薪，额外薪数、奖金、签字费及其他现金统一假设在 12 月发放。使用累计预扣法，专项扣除按所填缴费额计算；不含其他收入、减免税或年度汇算调整。实际到账以工资条和税务核算为准。保存 Offer 时一起保存估算参数。</p>
    </>}
  </section>;
}
