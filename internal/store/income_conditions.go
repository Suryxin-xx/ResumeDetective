package store

import (
	"context"
	"encoding/json"
	"errors"
	"math"
)

type IncomeTax struct {
	Enabled       bool    `json:"enabled"`
	Year          int     `json:"year"`
	SocialBase    float64 `json:"socialBase"`
	SocialRate    float64 `json:"socialRate"`
	FundBase      float64 `json:"fundBase"`
	FundRate      float64 `json:"fundRate"`
	Deduction     float64 `json:"deduction"`
	SeparateBonus float64 `json:"separateBonus"`
}
type IncomeSalary struct {
	MonthlySalary     float64 `json:"monthlySalary"`
	SalaryMonths      float64 `json:"salaryMonths"`
	Bonus             float64 `json:"bonus"`
	SigningBonus      float64 `json:"signingBonus"`
	OtherCompensation float64 `json:"otherCompensation"`
}
type IncomeConditions struct {
	Tax              *IncomeTax `json:"tax"`
	CustomBases      bool       `json:"customBases"`
	SocialBaseMode   string     `json:"socialBaseMode,omitempty"`
	FundBaseMode     string     `json:"fundBaseMode,omitempty"`
	EmployerFundRate float64    `json:"employerFundRate"`
	BonusEligible    bool       `json:"bonusEligible"`
	Method           string     `json:"method"`
	Hours            float64    `json:"hours"`
	Days             float64    `json:"days"`
	Confirmed        bool       `json:"confirmed"`
}
type IncomeParameters struct {
	Version int          `json:"version"`
	Salary  IncomeSalary `json:"salary"`
	IncomeConditions
}

func validateIncomeParameters(p IncomeParameters, allowIncomplete bool) error {
	if p.Tax == nil || p.Tax.Year < 2019 || p.Tax.Year > 2099 || (p.Method != "combined" && p.Method != "separate") {
		return errors.New("计税参数不完整")
	}
	for _, mode := range []string{p.SocialBaseMode, p.FundBaseMode} {
		if mode != "" && mode != "salary" && mode != "custom" {
			return errors.New("缴费基数模式无效")
		}
	}
	if p.Hours <= 0 || p.Hours > 24 || p.Days <= 0 || p.Days > 7 {
		return errors.New("请填写有效工时：每天 0–24 小时，每周 0–7 天（不含 0）")
	}
	s, t := p.Salary, p.Tax
	for _, v := range []float64{s.MonthlySalary, s.SalaryMonths, s.Bonus, s.SigningBonus, s.OtherCompensation, t.SocialBase, t.FundBase, t.Deduction, t.SeparateBonus, p.Hours, p.Days} {
		if math.IsNaN(v) || math.IsInf(v, 0) || v < 0 || v > 1e10 {
			return errors.New("金额或工时超出范围")
		}
	}
	for _, rate := range []float64{t.SocialRate, t.FundRate, p.EmployerFundRate} {
		if math.IsNaN(rate) || math.IsInf(rate, 0) || rate < 0 || rate > 100 {
			return errors.New("比例必须在 0–100 之间")
		}
	}
	if s.SalaryMonths < 1 || s.SalaryMonths > 120 {
		return errors.New("薪资月数必须在 1–120 之间")
	}
	if !allowIncomplete && (s.MonthlySalary <= 0 || s.SalaryMonths < 12) {
		return errors.New("完整年度估算需要月薪大于 0 且至少 12 薪")
	}
	if s.MonthlySalary*s.SalaryMonths+s.Bonus+s.SigningBonus+s.OtherCompensation > 1e10 {
		return errors.New("年度金额超出范围")
	}
	if p.BonusEligible && (t.SeparateBonus <= 0 || t.SeparateBonus > s.MonthlySalary*math.Max(0, s.SalaryMonths-12)+s.Bonus+0.001) {
		return errors.New("请检查符合条件的整笔全年一次性奖金金额")
	}
	if p.Method == "separate" && (!p.BonusEligible || t.Year > 2027) {
		return errors.New("单独计税需要符合条件的年终奖，且适用年份不超过 2027")
	}
	socialBase, fundBase := s.MonthlySalary, s.MonthlySalary
	if p.SocialBaseMode == "custom" || (p.SocialBaseMode == "" && p.CustomBases) {
		socialBase = t.SocialBase
	}
	if p.FundBaseMode == "custom" || (p.FundBaseMode == "" && p.CustomBases) {
		fundBase = t.FundBase
	}
	if s.MonthlySalary > 0 && socialBase*t.SocialRate/100+fundBase*t.FundRate/100 > s.MonthlySalary+0.001 {
		return errors.New("个人月缴费超过月薪，请检查基数和比例")
	}
	return nil
}

// Update only salary/calculation conditions; never overwrite notes or decision facts.
func (s *Store) UpdateOfferIncome(ctx context.Context, id int64, p IncomeParameters, expected string) error {
	if p.Version != 1 {
		return errors.New("收入参数版本不受支持")
	}
	if err := validateIncomeParameters(p, false); err != nil {
		return err
	}
	if expected == "" {
		return errors.New("请重新载入 Offer 后再保存")
	}
	raw, _ := json.Marshal(p.IncomeConditions)
	v := p.Salary
	res, err := s.db.ExecContext(ctx, `UPDATE offers SET monthly_salary=?,salary_months=?,bonus=?,signing_bonus=?,other_compensation=?,income_settings=?,updated_at=? WHERE id=? AND updated_at=?`, v.MonthlySalary, v.SalaryMonths, v.Bonus, v.SigningBonus, v.OtherCompensation, string(raw), nextOfferTimestamp(expected), id, expected)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("Offer 已被修改或删除，请重新载入后确认，未覆盖现有数据")
	}
	return nil
}
