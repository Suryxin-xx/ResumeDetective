package store

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"
)

func TestIncomePlansPersistAndUpgrade(t *testing.T) {
	path := filepath.Join(t.TempDir(), "data.db")
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	st.db.Exec("DROP TABLE income_plans; PRAGMA user_version=11;")
	st.Close()
	st, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	raw := json.RawMessage(`{"version":1,"salary":{"monthlySalary":15000,"salaryMonths":13,"bonus":0,"signingBonus":0,"otherCompensation":0},"tax":{"year":2026,"socialRate":10.5,"fundRate":5,"socialBase":0,"fundBase":0,"deduction":0,"separateBonus":0},"employerFundRate":5,"method":"combined","hours":8,"days":5}`)
	id, err := st.SaveIncomePlan(ctx, IncomePlan{Name: "方案 A", Parameters: raw})
	if err != nil {
		t.Fatal(err)
	}
	_, err = st.SaveIncomePlan(ctx, IncomePlan{ID: id, Name: "方案 B", Parameters: raw})
	if err != nil {
		t.Fatal(err)
	}
	st.Close()
	st, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	list, err := st.ListIncomePlans(ctx)
	if err != nil || len(list) != 1 || list[0].Name != "方案 B" {
		t.Fatalf("persistence: %#v %v", list, err)
	}
	if _, err = st.SaveIncomePlan(ctx, IncomePlan{Name: "bad", Parameters: json.RawMessage(`{"version":2}`)}); err == nil {
		t.Fatal("invalid accepted")
	}
	if _, err = st.SaveIncomePlan(ctx, IncomePlan{ID: id + 999, Name: "missing", Parameters: raw}); err == nil {
		t.Fatal("missing update accepted")
	}
	if err = st.DeleteIncomePlan(ctx, id); err != nil {
		t.Fatal(err)
	}
	list, _ = st.ListIncomePlans(ctx)
	if len(list) != 0 {
		t.Fatal("delete failed")
	}
	backups, _ := filepath.Glob(filepath.Join(filepath.Dir(path), "migration-backups", "before-schema12-*.db"))
	if len(backups) != 1 {
		t.Fatalf("backups=%v", backups)
	}
}
