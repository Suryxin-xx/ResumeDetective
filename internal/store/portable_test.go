package store

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestPortableRejectsNewerDatabaseAndMissingSource(t *testing.T) {
	path := filepath.Join(t.TempDir(), "source.db")
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = st.db.Exec("PRAGMA user_version=999"); err != nil {
		t.Fatal(err)
	}
	st.Close()
	if err = InspectPortable(path); err == nil {
		t.Fatal("future schema accepted")
	}
	missing := filepath.Join(t.TempDir(), "missing.db")
	target := filepath.Join(t.TempDir(), "target.db")
	if err = SnapshotPortable(context.Background(), missing, target); err == nil {
		t.Fatal("missing source accepted")
	}
	for _, p := range []string{missing, target} {
		if _, err = os.Stat(p); !os.IsNotExist(err) {
			t.Fatal("invalid import created DB")
		}
	}
}
func TestManagedRelativeRejectsExternalAndCrossSpaceReferences(t *testing.T) {
	base := t.TempDir()
	for _, p := range []string{filepath.Join(filepath.Dir(base), "foreign.pdf"), filepath.Join(base, "spaces", "other", "resumes", "x.pdf"), "../resumes/x.pdf", "config.json"} {
		if _, err := ManagedRelative(base, p); err == nil {
			t.Fatalf("accepted %q", p)
		}
	}
	if rel, err := ManagedRelative(base, filepath.Join(base, "resumes", "normal.pdf")); err != nil || rel != filepath.Join("resumes", "normal.pdf") {
		t.Fatalf("managed file rejected %q %v", rel, err)
	}
}

func TestPortableSnapshotSupportsWindowsUnicodeAndURIPunctuation(t *testing.T) {
	source := filepath.Join(t.TempDir(), "秋招 数据 # &.db")
	st, err := Open(source)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if _, err = st.CreateApplication(context.Background(), CreateApplicationInput{CompanyName: "中文路径", PositionName: "岗位"}); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(t.TempDir(), "副本 数据.db")
	if err = SnapshotPortable(context.Background(), source, target); err != nil {
		t.Fatal(err)
	}
	copy, err := Open(target)
	if err != nil {
		t.Fatal(err)
	}
	defer copy.Close()
	items, err := copy.ListApplications(context.Background())
	if err != nil || len(items) != 1 || items[0].CompanyName != "中文路径" {
		t.Fatalf("snapshot failed: %v %v", items, err)
	}
}
