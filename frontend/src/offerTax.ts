// Local-only estimate for a full calendar year of PRC resident employment.
// SAT 2018 No.61 cumulative withholding; annual bonus policy 2023 No.30.
export type TaxSettings = {
  enabled: boolean; year: number; socialBase: number; socialRate: number;
  fundBase: number; fundRate: number; deduction: number; separateBonus: number;
};
export const defaultTaxSettings = (): TaxSettings => ({ enabled: false, year: new Date().getFullYear(), socialBase: 0, socialRate: 0, fundBase: 0, fundRate: 0, deduction: 0, separateBonus: 0 });
export function readTaxSettings(raw?: string): TaxSettings {
  try { return { ...defaultTaxSettings(), ...JSON.parse(raw || "{}") }; } catch { return defaultTaxSettings(); }
}
export type SalaryInput = { monthlySalary: number; salaryMonths: number; bonus: number; signingBonus: number; otherCompensation: number };
const round = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;
const bands = [[36000, .03, 0], [144000, .1, 2520], [300000, .2, 16920], [420000, .25, 31920], [660000, .3, 52920], [960000, .35, 85920], [Infinity, .45, 181920]];
export function annualTax(income: number): number {
  const taxable = Math.max(0, income);
  const [, rate, deduction] = bands.find(([limit]) => taxable <= limit)!;
  return round(taxable * rate - deduction);
}
export function estimateOffer(s: SalaryInput, t: TaxSettings) {
  const values = [s.monthlySalary, s.salaryMonths, s.bonus, s.signingBonus, s.otherCompensation, t.socialBase, t.socialRate, t.fundBase, t.fundRate, t.deduction, t.separateBonus];
  if (values.some(v => !Number.isFinite(v) || v < 0)) return { error: "金额和比例必须是非负数。" } as const;
  if (s.monthlySalary <= 0 || s.salaryMonths < 12) return { error: "请填写月薪；完整年度估算需要至少 12 薪。" } as const;
  if (t.socialRate > 100 || t.fundRate > 100) return { error: "缴费比例不能超过 100%。" } as const;
  if (!Number.isInteger(t.year) || t.year < 2019 || t.year > 2099) return { error: "请填写有效的计算年份（2019–2099）。" } as const;
  if (t.separateBonus > 0 && t.year > 2027) return { error: "2027 年之后的年终奖单独计税政策尚未配置，请设为 0 并按综合所得估算。" } as const;
  const extras = round(s.monthlySalary * (s.salaryMonths - 12) + s.bonus);
  if (t.separateBonus > extras) return { error: "单独计税奖金不能超过额外薪数与年度奖金合计；签字费不计入此额度。" } as const;
  const social = round(t.socialBase * t.socialRate / 100);
  const fund = round(t.fundBase * t.fundRate / 100);
  if (social + fund > s.monthlySalary) return { error: "个人月缴费超过月薪，请检查基数和比例。" } as const;
  const gross = round(s.monthlySalary * s.salaryMonths + s.bonus + s.signingBonus + s.otherCompensation);
  if (!Number.isFinite(gross) || gross > 1e10) return { error: "金额超出估算范围，请检查输入单位。" } as const;
  const [, bonusRate, bonusDeduction] = bands.find(([limit]) => t.separateBonus <= limit)!;
  const bonusTax = t.separateBonus ? round(t.separateBonus * bonusRate - bonusDeduction / 12) : 0;
  let paid = 0;
  let accumulated = 0;
  const months = Array.from({ length: 12 }, (_, i) => {
    const extra = i === 11 ? extras + s.signingBonus + s.otherCompensation - t.separateBonus : 0;
    const income = round(s.monthlySalary + extra);
    accumulated += income;
    const tax = round(Math.max(0, annualTax(accumulated - (i + 1) * (5000 + social + fund + t.deduction)) - paid));
    paid = round(paid + tax);
    const separate = i === 11 ? t.separateBonus : 0;
    const separateTax = i === 11 ? bonusTax : 0;
    return { month: i + 1, gross: round(income + separate), contributions: round(social + fund), tax: round(tax + separateTax), net: round(income + separate - social - fund - tax - separateTax) };
  });
  const tax = round(paid + bonusTax);
  const net = round(gross - (social + fund) * 12 - tax);
  return { gross, net, average: round(net / 12), tax, social: round(social * 12), fund: round(fund * 12), months };
}

// Compare the complete qualifying bonus, never optimize by splitting one bonus.
type SuccessfulEstimate = Extract<ReturnType<typeof estimateOffer>, { net: number }>;
export function compareBonusTax(s: SalaryInput, t: TaxSettings):
  { ok: false; error: string } | { ok: true; error?: undefined; combined: SuccessfulEstimate; separate: SuccessfulEstimate; saving: number; recommended: "separate" | "combined" | "equal" } {
  const combined = estimateOffer(s, { ...t, separateBonus: 0 });
  const separate = estimateOffer(s, t);
  if (combined.error || separate.error) return { ok: false, error: combined.error || separate.error || "请检查计税参数。" };
  const saving = round(combined.tax - separate.tax);
  return { ok: true, combined, separate, saving: Math.abs(saving), recommended: saving > 0 ? "separate" : saving < 0 ? "combined" : "equal" };
}
export function housingFund(base: number, personalRate: number, employerRate: number) {
  if ([base, personalRate, employerRate].some(n => !Number.isFinite(n) || n < 0) || base > 1e10 || personalRate > 100 || employerRate > 100) return { error: "请检查公积金基数和缴存比例。" } as const;
  const personal = round(base * personalRate / 100), employer = round(base * employerRate / 100);
  const monthly = round(personal + employer);
  return { personal, employer, monthly, annual: round(monthly * 12) };
}
