package store

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"strings"
	"time"
)

type Offer struct {
	ID                int64   `json:"id"`
	ApplicationID     int64   `json:"applicationId"`
	CompanyName       string  `json:"companyName"`
	PositionName      string  `json:"positionName"`
	Department        string  `json:"department"`
	Location          string  `json:"location"`
	MonthlySalary     float64 `json:"monthlySalary"`
	SalaryMonths      float64 `json:"salaryMonths"`
	Bonus             float64 `json:"bonus"`
	SigningBonus      float64 `json:"signingBonus"`
	OtherCompensation float64 `json:"otherCompensation"`
	WorkIntensity     int     `json:"workIntensity"`
	GrowthScore       int     `json:"growthScore"`
	InterestScore     int     `json:"interestScore"`
	LocationScore     int     `json:"locationScore"`
	StabilityScore    int     `json:"stabilityScore"`
	DecisionStatus    string  `json:"decisionStatus"`
	Deadline          string  `json:"deadline"`
	Notes             string  `json:"notes"`
	TaxSettings       string  `json:"taxSettings"`
	UpdatedAt         string  `json:"updatedAt"`
}

type UpsertOfferInput struct {
	ApplicationID     int64   `json:"applicationId"`
	Department        string  `json:"department"`
	Location          string  `json:"location"`
	MonthlySalary     float64 `json:"monthlySalary"`
	SalaryMonths      float64 `json:"salaryMonths"`
	Bonus             float64 `json:"bonus"`
	SigningBonus      float64 `json:"signingBonus"`
	OtherCompensation float64 `json:"otherCompensation"`
	WorkIntensity     int     `json:"workIntensity"`
	GrowthScore       int     `json:"growthScore"`
	InterestScore     int     `json:"interestScore"`
	LocationScore     int     `json:"locationScore"`
	StabilityScore    int     `json:"stabilityScore"`
	DecisionStatus    string  `json:"decisionStatus"`
	Deadline          string  `json:"deadline"`
	Notes             string  `json:"notes"`
	TaxSettings       string  `json:"taxSettings"`
}

func (s *Store) ListOffers(ctx context.Context) ([]Offer, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT o.id,o.application_id,r.company_name,r.position_name,o.department,o.location,o.monthly_salary,o.salary_months,o.bonus,o.signing_bonus,o.other_compensation,o.work_intensity,o.growth_score,o.interest_score,o.location_score,o.stability_score,o.decision_status,o.deadline,o.notes,COALESCE(o.tax_settings,''),o.updated_at FROM offers o JOIN applications a ON a.id=o.application_id JOIN resumes r ON r.id=a.resume_id ORDER BY (o.monthly_salary*o.salary_months+o.bonus+o.signing_bonus+o.other_compensation) DESC,o.updated_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []Offer{}
	for rows.Next() {
		var item Offer
		if err := rows.Scan(&item.ID, &item.ApplicationID, &item.CompanyName, &item.PositionName, &item.Department, &item.Location, &item.MonthlySalary, &item.SalaryMonths, &item.Bonus, &item.SigningBonus, &item.OtherCompensation, &item.WorkIntensity, &item.GrowthScore, &item.InterestScore, &item.LocationScore, &item.StabilityScore, &item.DecisionStatus, &item.Deadline, &item.Notes, &item.TaxSettings, &item.UpdatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) UpsertOffer(ctx context.Context, in UpsertOfferInput) (int64, error) {
	if in.ApplicationID < 1 {
		return 0, errors.New("请选择对应的 Offer 岗位")
	}
	for _, score := range []int{in.WorkIntensity, in.GrowthScore, in.InterestScore, in.LocationScore, in.StabilityScore} {
		if score < 1 || score > 5 {
			return 0, errors.New("评分必须在 1 到 5 之间")
		}
	}
	if in.SalaryMonths <= 0 {
		in.SalaryMonths = 12
	}
	if in.DecisionStatus == "" {
		in.DecisionStatus = "考虑中"
	}
	var exists int
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM applications WHERE id=?", in.ApplicationID).Scan(&exists); err != nil {
		return 0, err
	}
	if exists == 0 {
		return 0, errors.New("对应投递不存在")
	}
	if err := validateOfferTaxSettings(in.TaxSettings); err != nil {
		return 0, err
	}
	now := time.Now().Format(time.RFC3339)
	_, err := s.db.ExecContext(ctx, `INSERT INTO offers(application_id,department,location,monthly_salary,salary_months,bonus,signing_bonus,other_compensation,work_intensity,growth_score,interest_score,location_score,stability_score,decision_status,deadline,notes,tax_settings,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(application_id) DO UPDATE SET department=excluded.department,location=excluded.location,monthly_salary=excluded.monthly_salary,salary_months=excluded.salary_months,bonus=excluded.bonus,signing_bonus=excluded.signing_bonus,other_compensation=excluded.other_compensation,work_intensity=excluded.work_intensity,growth_score=excluded.growth_score,interest_score=excluded.interest_score,location_score=excluded.location_score,stability_score=excluded.stability_score,decision_status=excluded.decision_status,deadline=excluded.deadline,notes=excluded.notes,tax_settings=excluded.tax_settings,updated_at=excluded.updated_at`, in.ApplicationID, strings.TrimSpace(in.Department), strings.TrimSpace(in.Location), in.MonthlySalary, in.SalaryMonths, in.Bonus, in.SigningBonus, in.OtherCompensation, in.WorkIntensity, in.GrowthScore, in.InterestScore, in.LocationScore, in.StabilityScore, strings.TrimSpace(in.DecisionStatus), strings.TrimSpace(in.Deadline), strings.TrimSpace(in.Notes), in.TaxSettings, now)
	if err != nil {
		return 0, err
	}
	var id int64
	err = s.db.QueryRowContext(ctx, "SELECT id FROM offers WHERE application_id=?", in.ApplicationID).Scan(&id)
	return id, err
}

func (s *Store) DeleteOffer(ctx context.Context, id int64) error {
	result, err := s.db.ExecContext(ctx, "DELETE FROM offers WHERE id=?", id)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return errors.New("Offer 记录不存在")
	}
	return nil
}

func validateOfferTaxSettings(raw string) error {
	if raw == "" {
		return nil
	}
	if len(raw) > 4096 {
		return errors.New("到手估算参数过长")
	}
	var settings struct {
		Enabled       bool    `json:"enabled"`
		Year          int     `json:"year"`
		SocialBase    float64 `json:"socialBase"`
		SocialRate    float64 `json:"socialRate"`
		FundBase      float64 `json:"fundBase"`
		FundRate      float64 `json:"fundRate"`
		Deduction     float64 `json:"deduction"`
		SeparateBonus float64 `json:"separateBonus"`
	}
	if err := json.Unmarshal([]byte(raw), &settings); err != nil {
		return errors.New("到手估算参数格式错误")
	}
	for _, v := range []float64{settings.SocialBase, settings.SocialRate, settings.FundBase, settings.FundRate, settings.Deduction, settings.SeparateBonus} {
		if math.IsNaN(v) || math.IsInf(v, 0) || v < 0 {
			return errors.New("到手估算金额和比例不能为负数")
		}
	}
	if settings.SocialRate > 100 || settings.FundRate > 100 {
		return errors.New("缴费比例不能超过 100%")
	}
	if settings.Enabled && (settings.Year < 2019 || settings.Year > 2099) {
		return errors.New("请填写有效的估算年份")
	}
	return nil
}
