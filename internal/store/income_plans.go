package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
)

func ensureIncomePlans(db *sql.DB) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.Exec(`CREATE TABLE IF NOT EXISTS income_plans (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, parameters TEXT NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
 PRAGMA user_version = 12;`); err != nil {
		return err
	}
	return tx.Commit()
}

type IncomePlan struct {
	ID         int64           `json:"id"`
	Name       string          `json:"name"`
	Parameters json.RawMessage `json:"parameters"`
	UpdatedAt  string          `json:"updatedAt"`
}

func (s *Store) ListIncomePlans(ctx context.Context) ([]IncomePlan, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT id,name,parameters,updated_at FROM income_plans ORDER BY updated_at DESC,id DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []IncomePlan{}
	for rows.Next() {
		var p IncomePlan
		var raw string
		if err := rows.Scan(&p.ID, &p.Name, &raw, &p.UpdatedAt); err != nil {
			return nil, err
		}
		p.Parameters = json.RawMessage(raw)
		items = append(items, p)
	}
	return items, rows.Err()
}

func (s *Store) SaveIncomePlan(ctx context.Context, p IncomePlan) (int64, error) {
	p.Name = strings.TrimSpace(p.Name)
	if p.ID < 0 || p.Name == "" || len([]rune(p.Name)) > 80 || len(p.Parameters) > 16384 {
		return 0, errors.New("方案名称需为 1–80 字，参数不能过长")
	}
	var params struct {
		Version int `json:"version"`
		Salary  struct {
			MonthlySalary     float64 `json:"monthlySalary"`
			SalaryMonths      float64 `json:"salaryMonths"`
			Bonus             float64 `json:"bonus"`
			SigningBonus      float64 `json:"signingBonus"`
			OtherCompensation float64 `json:"otherCompensation"`
		} `json:"salary"`
		Tax *struct {
			Year          int     `json:"year"`
			SocialBase    float64 `json:"socialBase"`
			SocialRate    float64 `json:"socialRate"`
			FundBase      float64 `json:"fundBase"`
			FundRate      float64 `json:"fundRate"`
			Deduction     float64 `json:"deduction"`
			SeparateBonus float64 `json:"separateBonus"`
		} `json:"tax"`
		CustomBases      bool    `json:"customBases"`
		EmployerFundRate float64 `json:"employerFundRate"`
		BonusEligible    bool    `json:"bonusEligible"`
		Method           string  `json:"method"`
		Hours            float64 `json:"hours"`
		Days             float64 `json:"days"`
	}
	if json.Unmarshal(p.Parameters, &params) != nil || params.Version != 1 || params.Salary.MonthlySalary <= 0 || params.Salary.SalaryMonths < 12 || params.Hours <= 0 || params.Hours > 24 || params.Days <= 0 || params.Days > 7 {
		return 0, errors.New("收入方案参数无效或版本不受支持")
	}
	if params.Tax == nil || params.Tax.Year < 2019 || params.Tax.Year > 2099 || (params.Method != "combined" && params.Method != "separate") {
		return 0, errors.New("计税参数不完整")
	}
	for _, value := range []float64{params.Salary.MonthlySalary, params.Salary.Bonus, params.Salary.SigningBonus, params.Salary.OtherCompensation, params.Tax.SocialBase, params.Tax.FundBase, params.Tax.Deduction, params.Tax.SeparateBonus} {
		if value < 0 || value > 1e10 {
			return 0, errors.New("金额超出范围")
		}
	}
	for _, rate := range []float64{params.Tax.SocialRate, params.Tax.FundRate, params.EmployerFundRate} {
		if rate < 0 || rate > 100 {
			return 0, errors.New("比例必须在 0–100 之间")
		}
	}
	if params.Salary.MonthlySalary*params.Salary.SalaryMonths+params.Salary.Bonus+params.Salary.SigningBonus+params.Salary.OtherCompensation > 1e10 {
		return 0, errors.New("年度金额超出范围")
	}
	if params.BonusEligible && (params.Tax.Year > 2027 || params.Tax.SeparateBonus <= 0 || params.Tax.SeparateBonus > params.Salary.MonthlySalary*(params.Salary.SalaryMonths-12)+params.Salary.Bonus+0.001) {
		return 0, errors.New("请检查全年一次性奖金金额及适用年份")
	}
	// Store a complete canonical parameter object, not arbitrary caller JSON.
	p.Parameters, _ = json.Marshal(params)
	// Store a complete canonical parameter object, not arbitrary caller JSON.
	p.Parameters, _ = json.Marshal(params)
	if p.ID == 0 {
		res, err := s.db.ExecContext(ctx, "INSERT INTO income_plans(name,parameters) VALUES(?,?)", p.Name, string(p.Parameters))
		if err != nil {
			return 0, err
		}
		return res.LastInsertId()
	}
	res, err := s.db.ExecContext(ctx, "UPDATE income_plans SET name=?,parameters=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", p.Name, string(p.Parameters), p.ID)
	if err != nil {
		return 0, err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, err
	}
	if n == 0 {
		return 0, errors.New("方案不存在，请另存为新方案")
	}
	return p.ID, nil
}

func (s *Store) DeleteIncomePlan(ctx context.Context, id int64) error {
	_, err := s.db.ExecContext(ctx, "DELETE FROM income_plans WHERE id=?", id)
	return err
}
