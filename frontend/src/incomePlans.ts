import { defaultTaxSettings, type SalaryInput, type TaxSettings } from "./offerTax";
export type IncomeParameters = {
  version: 1; salary: SalaryInput; tax: TaxSettings; customBases: boolean;
  hours: number; days: number; employerFundRate: number; bonusEligible: boolean;
  method: "combined" | "separate";
};
export type IncomePlan = { id: number; name: string; parameters: IncomeParameters; updatedAt: string };
export const emptyIncome = (): IncomeParameters => ({
  version: 1, salary: { monthlySalary: 0, salaryMonths: 12, bonus: 0, signingBonus: 0, otherCompensation: 0 },
  tax: { ...defaultTaxSettings(), enabled: true, socialRate: 10.5, fundRate: 5 },
  customBases: false, hours: 8, days: 5, employerFundRate: 5, bonusEligible: false, method: "combined",
});
