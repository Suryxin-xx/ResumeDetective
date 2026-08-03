package store

import (
	"context"
	"path/filepath"
	"testing"
)

func TestClearDemoKeepsUnmarkedUserRecords(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "demo.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	demoID, err := st.CreateApplication(ctx, CreateApplicationInput{CompanyName: "演示公司", PositionName: "演示岗位"})
	if err != nil {
		t.Fatal(err)
	}
	demoApp, err := st.GetApplication(ctx, demoID)
	if err != nil {
		t.Fatal(err)
	}
	if err := st.MarkDemo(ctx, "application", demoID); err != nil {
		t.Fatal(err)
	}
	if err := st.MarkDemo(ctx, "resume", demoApp.ResumeID); err != nil {
		t.Fatal(err)
	}
	if _, err := st.CreateApplication(ctx, CreateApplicationInput{CompanyName: "真实公司", PositionName: "真实岗位"}); err != nil {
		t.Fatal(err)
	}
	dashboard, err := st.Dashboard(ctx)
	if err != nil || !dashboard.Demo {
		t.Fatalf("dashboard=%+v err=%v", dashboard, err)
	}
	if err := st.ClearDemo(ctx); err != nil {
		t.Fatal(err)
	}
	items, err := st.ListApplications(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].CompanyName != "真实公司" {
		t.Fatalf("unexpected remaining records: %+v", items)
	}
}
