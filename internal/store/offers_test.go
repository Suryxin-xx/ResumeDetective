package store

import (
	"context"
	"path/filepath"
	"testing"
)

func TestOfferRoundTrip(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "offers.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	applicationID, err := st.CreateApplication(ctx, CreateApplicationInput{CompanyName: "测试公司", PositionName: "测试岗位", CurrentStatus: "Offer", StageState: "已完成"})
	if err != nil {
		t.Fatal(err)
	}
	id, err := st.UpsertOffer(ctx, UpsertOfferInput{ApplicationID: applicationID, MonthlySalary: 20000, SalaryMonths: 14, WorkIntensity: 3, GrowthScore: 4, InterestScore: 4, LocationScore: 3, StabilityScore: 4, DecisionStatus: "考虑中"})
	if err != nil || id < 1 {
		t.Fatalf("upsert id=%d err=%v", id, err)
	}
	items, err := st.ListOffers(ctx)
	if err != nil || len(items) != 1 || items[0].CompanyName != "测试公司" || items[0].MonthlySalary != 20000 {
		t.Fatalf("offers=%#v err=%v", items, err)
	}
	if _, err := st.UpsertOffer(ctx, UpsertOfferInput{ApplicationID: applicationID, MonthlySalary: 22000, SalaryMonths: 14, WorkIntensity: 2, GrowthScore: 5, InterestScore: 4, LocationScore: 3, StabilityScore: 4, DecisionStatus: "倾向接受"}); err != nil {
		t.Fatal(err)
	}
	items, _ = st.ListOffers(ctx)
	if len(items) != 1 || items[0].MonthlySalary != 22000 || items[0].DecisionStatus != "倾向接受" {
		t.Fatalf("updated offer=%#v", items)
	}
}
