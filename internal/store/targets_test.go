package store

import (
	"context"
	"path/filepath"
	"testing"
)

func TestJobTargetConvertsAtomically(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "targets.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	targetID, err := st.CreateJobTarget(ctx, JobTargetInput{CompanyName: "意向公司", PositionName: "供应链", Status: "待投递", JDText: "JD", Priority: 3})
	if err != nil {
		t.Fatal(err)
	}
	applicationID, err := st.ConvertJobTarget(ctx, targetID, ConvertTargetInput{Source: "官网", Category: "供应链", Tags: "校招", AppliedAt: "2026-08-02"})
	if err != nil {
		t.Fatal(err)
	}
	if applicationID < 1 {
		t.Fatalf("application id = %d", applicationID)
	}
	applications, err := st.ListApplications(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(applications) != 1 || applications[0].CompanyName != "意向公司" || applications[0].CurrentStatus != "已投递" || applications[0].Category != "供应链" {
		t.Fatalf("unexpected applications: %+v", applications)
	}
	targets, err := st.ListJobTargets(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(targets) != 1 || targets[0].Status != "已投递" {
		t.Fatalf("unexpected targets: %+v", targets)
	}
	if _, err := st.ConvertJobTarget(ctx, targetID, ConvertTargetInput{}); err == nil {
		t.Fatal("second conversion should fail")
	}
}

func TestOpenRepairsLegacyTargetColumnShift(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy-targets.db")
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	_, err = st.db.Exec(`INSERT INTO job_targets(company_name,position_name,status,priority,sort_order,created_at,updated_at) VALUES('旧公司','旧岗位','待研究','2026-07-11 07:33:29','2026-07-11 08:00:00',0,0)`)
	if err != nil {
		t.Fatal(err)
	}
	_ = st.Close()
	st, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	items, err := st.ListJobTargets(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].Priority != 0 || items[0].CreatedAt != "2026-07-11 07:33:29" || items[0].UpdatedAt != "2026-07-11 08:00:00" {
		t.Fatalf("legacy row not repaired: %+v", items)
	}
}
