package store

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"
	"time"
)

const incomeTestJSON = `{"version":1,"salary":{"monthlySalary":15000,"salaryMonths":13},"tax":{"enabled":true,"year":2026,"socialRate":10.5,"fundRate":8,"socialBase":10000,"fundBase":12000},"socialBaseMode":"salary","fundBaseMode":"custom","employerFundRate":12,"method":"combined","hours":8,"days":5,"confirmed":true}`

func TestOfferTimestampAlwaysAdvances(t *testing.T) {
	previous := time.Now().Add(time.Second).Format(time.RFC3339Nano)
	for i := 0; i < 10; i++ {
		next := nextOfferTimestamp(previous)
		a, _ := time.Parse(time.RFC3339Nano, previous)
		b, _ := time.Parse(time.RFC3339Nano, next)
		if !b.After(a) {
			t.Fatal("timestamp reused")
		}
		previous = next
	}
}

func TestCreateOnlyOfferDoesNotOverwriteExistingFacts(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	_, err = st.db.Exec(`INSERT INTO resumes(id,company_name,position_name,file_path) VALUES(1,'示例公司','研发',''); INSERT INTO applications(id,resume_id,current_status) VALUES(1,1,'Offer');`)
	if err != nil {
		t.Fatal(err)
	}
	in := UpsertOfferInput{CreateOnly: true, ApplicationID: 1, MonthlySalary: 15000, SalaryMonths: 13, WorkIntensity: 3, GrowthScore: 3, InterestScore: 3, LocationScore: 3, StabilityScore: 3, Notes: "原始备注"}
	if _, err = st.UpsertOffer(ctx, in); err != nil {
		t.Fatal(err)
	}
	before, err := st.ListOffers(ctx)
	if err != nil {
		t.Fatal(err)
	}
	in.MonthlySalary = 20000
	in.Notes = "过期新增页"
	if _, err = st.UpsertOffer(ctx, in); err == nil {
		t.Fatal("duplicate create overwrote existing offer")
	}
	after, err := st.ListOffers(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(after) != 1 || after[0] != before[0] {
		t.Fatal("existing offer facts changed")
	}
	in.CreateOnly = false
	in.ExpectedUpdatedAt = after[0].UpdatedAt
	if _, err = st.UpsertOffer(ctx, in); err != nil {
		t.Fatal("explicit edit failed:", err)
	}
}

func TestOfferIncomeConditionsAndLinkedPlans(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	_, err = st.db.Exec(`INSERT INTO resumes(id,company_name,position_name,file_path) VALUES(1,'示例公司','研发',''); INSERT INTO applications(id,resume_id,current_status) VALUES(1,1,'Offer'); INSERT INTO offers(id,application_id,monthly_salary,notes,decision_status) VALUES(1,1,12000,'保留原备注','倾向接受');`)
	if err != nil {
		t.Fatal(err)
	}
	offers, err := st.ListOffers(ctx)
	if err != nil {
		t.Fatal(err)
	}
	original := offers[0]
	var params IncomeParameters
	if err = json.Unmarshal([]byte(incomeTestJSON), &params); err != nil {
		t.Fatal(err)
	}
	if err = st.UpdateOfferIncome(ctx, 1, params, original.UpdatedAt); err != nil {
		t.Fatal(err)
	}
	if err = st.UpdateOfferIncome(ctx, 1, params, original.UpdatedAt); err == nil {
		t.Fatal("stale update accepted")
	}
	offers, _ = st.ListOffers(ctx)
	current := offers[0]
	legacyUpdate := UpsertOfferInput{ApplicationID: 1, MonthlySalary: 15000, SalaryMonths: 13, WorkIntensity: 3, GrowthScore: 3, InterestScore: 3, LocationScore: 3, StabilityScore: 3, DecisionStatus: "倾向接受", Notes: "保留原备注"}
	if _, err = st.UpsertOffer(ctx, legacyUpdate); err != nil {
		t.Fatal(err)
	}
	offers, _ = st.ListOffers(ctx)
	if offers[0].IncomeSettings != current.IncomeSettings {
		t.Fatal("legacy client erased calculation conditions")
	}
	current = offers[0]
	if current.MonthlySalary != 15000 || current.Notes != "保留原备注" || current.DecisionStatus != "倾向接受" {
		t.Fatalf("facts changed: %#v", current)
	}
	var conditions IncomeConditions
	json.Unmarshal([]byte(current.IncomeSettings), &conditions)
	if conditions.Tax.FundRate != 8 || conditions.EmployerFundRate != 12 || conditions.FundBaseMode != "custom" || conditions.SocialBaseMode != "salary" {
		t.Fatalf("conditions lost: %#v", conditions)
	}
	id := int64(1)
	_, err = st.SaveIncomePlan(ctx, IncomePlan{Name: "关联方案", OfferID: &id, SourceUpdatedAt: current.UpdatedAt, Parameters: json.RawMessage(incomeTestJSON)})
	if err != nil {
		t.Fatal(err)
	}
	plans, _ := st.ListIncomePlans(ctx)
	if len(plans) != 1 || plans[0].OfferID == nil || *plans[0].OfferID != 1 || plans[0].SourceUpdatedAt != current.UpdatedAt {
		t.Fatalf("link lost: %#v", plans)
	}
	bad := params
	bad.Tax = &IncomeTax{Year: 2026, FundRate: 101}
	if st.UpdateOfferIncome(ctx, 1, bad, current.UpdatedAt) == nil {
		t.Fatal("invalid rate accepted")
	}
	in := UpsertOfferInput{ApplicationID: 1, MonthlySalary: -1, SalaryMonths: 12, WorkIntensity: 3, GrowthScore: 3, InterestScore: 3, LocationScore: 3, StabilityScore: 3}
	if _, err = st.UpsertOffer(ctx, in); err == nil {
		t.Fatal("negative salary accepted")
	}
	if err = st.DeleteOffer(ctx, 1); err != nil {
		t.Fatal(err)
	}
	plans, _ = st.ListIncomePlans(ctx)
	if len(plans) != 1 || plans[0].OfferID != nil {
		t.Fatalf("deleting offer must preserve trial: %#v", plans)
	}
}

func TestSchema13PreservesLegacyOfferAndPlan(t *testing.T) {
	path := filepath.Join(t.TempDir(), "old.db")
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	_, err = st.db.Exec(`DROP TABLE income_plans;
 CREATE TABLE income_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,parameters TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
 INSERT INTO income_plans(id,name,parameters) VALUES(7,'旧独立方案','{}');
 INSERT INTO resumes(id,company_name,position_name,file_path) VALUES(1,'旧公司','旧岗位','');
 INSERT INTO applications(id,resume_id,current_status) VALUES(1,1,'Offer');
 INSERT INTO offers(id,application_id,monthly_salary,notes,tax_settings) VALUES(3,1,12000,'原始备注','{"enabled":true,"year":2026,"fundRate":7}');
 ALTER TABLE offers DROP COLUMN income_settings; PRAGMA user_version=12;`)
	if err != nil {
		t.Fatal(err)
	}
	st.Close()
	st, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	offers, _ := st.ListOffers(context.Background())
	plans, _ := st.ListIncomePlans(context.Background())
	if len(offers) != 1 || offers[0].MonthlySalary != 12000 || offers[0].Notes != "原始备注" || offers[0].IncomeSettings != "" || offers[0].TaxSettings == "" {
		t.Fatalf("offer migration: %#v", offers)
	}
	if len(plans) != 1 || plans[0].ID != 7 || plans[0].Name != "旧独立方案" || plans[0].OfferID != nil || string(plans[0].Parameters) != "{}" {
		t.Fatalf("plan migration: %#v", plans)
	}
	backups, _ := filepath.Glob(filepath.Join(filepath.Dir(path), "migration-backups", "before-schema13-*.db"))
	if len(backups) != 1 {
		t.Fatalf("backup missing: %v", backups)
	}
}
