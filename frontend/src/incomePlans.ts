import { defaultTaxSettings, estimateOffer, housingFund, type SalaryInput, type TaxSettings } from "./offerTax";
import type { Offer } from "./types";

export type IncomeConditions = {
  tax: TaxSettings; customBases: boolean; socialBaseMode?: "salary" | "custom"; fundBaseMode?: "salary" | "custom";
  hours: number; days: number; employerFundRate: number; bonusEligible: boolean;
  method: "combined" | "separate"; confirmed?: boolean;
};
export type IncomeParameters = IncomeConditions & { version: 1; salary: SalaryInput };
export type IncomePlan = { id: number; name: string; parameters: IncomeParameters; updatedAt: string; offerId?: number | null; sourceUpdatedAt?: string };
export const emptyIncome = (): IncomeParameters => ({
  version: 1, salary: { monthlySalary: 0, salaryMonths: 12, bonus: 0, signingBonus: 0, otherCompensation: 0 },
  tax: { ...defaultTaxSettings(), enabled: true, socialRate: 10.5, fundRate: 5 },
  customBases: false, socialBaseMode: "salary", fundBaseMode: "salary", hours: 8, days: 5,
  employerFundRate: 5, bonusEligible: false, method: "combined", confirmed: false,
});

export function normalizeIncome(raw: Partial<IncomeParameters>): IncomeParameters {
  const defaults = emptyIncome();
  const custom = raw.customBases === true;
  return { ...defaults, ...raw, version: 1,
    salary: { ...defaults.salary, ...raw.salary }, tax: { ...defaults.tax, ...raw.tax, enabled: true },
    socialBaseMode: raw.socialBaseMode ?? (custom ? "custom" : "salary"),
    fundBaseMode: raw.fundBaseMode ?? (custom ? "custom" : "salary"),
  };
}
export function fromOffer(offer?: Offer): IncomeParameters {
  if (!offer) return emptyIncome();
  let conditions: Partial<IncomeParameters> = {};
  try {
    if (offer.incomeSettings) conditions = JSON.parse(offer.incomeSettings);
    else if (offer.taxSettings) {
      const tax = JSON.parse(offer.taxSettings) as Partial<TaxSettings>;
      if (tax && typeof tax === "object" && tax.enabled) conditions = { tax: { ...emptyIncome().tax, ...tax },
        socialBaseMode: "custom", fundBaseMode: "custom", confirmed: false,
        bonusEligible: Number(tax.separateBonus) > 0, method: Number(tax.separateBonus) > 0 ? "separate" : "combined" };
    }
  } catch { /* Keep malformed historical settings untouched and show default estimates. */ }
  return normalizeIncome({ ...conditions, salary: { monthlySalary: offer.monthlySalary, salaryMonths: offer.salaryMonths || 12,
    bonus: offer.bonus, signingBonus: offer.signingBonus, otherCompensation: offer.otherCompensation } });
}
export function incomeConditions(p: IncomeParameters): IncomeConditions {
  const { salary: _salary, version: _version, ...conditions } = normalizeIncome(p);
  return conditions;
}
export function effectiveTax(p: IncomeParameters): TaxSettings {
  const value = normalizeIncome(p);
  return { ...value.tax, enabled: true,
    socialBase: value.socialBaseMode === "custom" ? value.tax.socialBase : value.salary.monthlySalary,
    fundBase: value.fundBaseMode === "custom" ? value.tax.fundBase : value.salary.monthlySalary,
    separateBonus: value.bonusEligible && value.method === "separate" ? value.tax.separateBonus : 0 };
}
export function incomeSummary(p: IncomeParameters) {
  const tax = effectiveTax(p);
  const result = estimateOffer(p.salary, tax);
  const fund = housingFund(tax.fundBase, tax.fundRate, p.employerFundRate);
  const validHours = Number.isFinite(p.hours) && p.hours > 0 && p.hours <= 24 && Number.isFinite(p.days) && p.days > 0 && p.days <= 7;
  return { tax, result, fund, validHours, hourly: !result.error && validHours ? result.net / (p.hours * p.days * 52) : null };
}
