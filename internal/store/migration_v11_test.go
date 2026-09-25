package store

import (
	"context"
	"path/filepath"
	"testing"
)

func TestOfferTaxMigrationAndRoundTrip(t *testing.T) {
	path := filepath.Join(t.TempDir(), "old.db")
	seed, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	_, err = seed.db.Exec(`INSERT INTO resumes(id,company_name,position_name,file_path) VALUES(1,'旧公司','旧岗位','');
 INSERT INTO applications(id,resume_id,current_status) VALUES(1,1,'Offer');
 INSERT INTO offers(application_id,monthly_salary,notes) VALUES(1,12000,'保留备注');
 ALTER TABLE offers DROP COLUMN tax_settings;
 PRAGMA user_version=10;`)
	if err != nil {
		t.Fatal(err)
	}
	seed.Close()
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	backups, err := filepath.Glob(filepath.Join(filepath.Dir(path), "migration-backups", "before-schema12-*.db"))
	if err != nil || len(backups) != 1 {
		t.Fatalf("missing migration backup: %v %v", backups, err)
	}
	items, err := st.ListOffers(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].MonthlySalary != 12000 || items[0].Notes != "保留备注" || items[0].TaxSettings != "" {
		t.Fatalf("migration changed data: %#v", items)
	}
	raw := `{"enabled":true,"year":2026,"socialBase":12000,"socialRate":10,"fundBase":12000,"fundRate":7}`
	input := UpsertOfferInput{ApplicationID: 1, MonthlySalary: 12000, SalaryMonths: 12, Notes: "保留备注", TaxSettings: raw, WorkIntensity: 3, GrowthScore: 3, InterestScore: 3, LocationScore: 3, StabilityScore: 3}
	if _, err = st.UpsertOffer(context.Background(), input); err != nil {
		t.Fatal(err)
	}
	items, err = st.ListOffers(context.Background())
	if err != nil || items[0].TaxSettings != raw {
		t.Fatalf("round trip failed: %#v %v", items, err)
	}
	input.TaxSettings = `{"socialRate":101}`
	if _, err = st.UpsertOffer(context.Background(), input); err == nil {
		t.Fatal("invalid rate accepted")
	}
	var version int
	st.db.QueryRow("PRAGMA user_version").Scan(&version)
	if version != SchemaVersion {
		t.Fatalf("version=%d", version)
	}
}
