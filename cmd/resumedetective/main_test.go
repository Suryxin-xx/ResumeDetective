package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestArchiveFullBackupsPreservesFilesAndManualBackups(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"automatic-1.space.zip", "automatic-2.space.zip", "automatic-3.space.zip", "manual.space.zip", "legacy.db"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(name), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := archiveOldSpaceBackups(dir, 2); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"automatic-2.space.zip", "automatic-3.space.zip", "manual.space.zip", "legacy.db", "retired/automatic-1.space.zip"} {
		b, err := os.ReadFile(filepath.Join(dir, filepath.FromSlash(name)))
		if err != nil || len(b) == 0 {
			t.Fatalf("lost %s: %v", name, err)
		}
	}
}

func TestPruneAutomaticBackupsKeepsNewestAndManualFiles(t *testing.T) {
	dir := t.TempDir()
	base := time.Now().Add(-time.Hour)
	for index, name := range []string{"automatic-1.db", "automatic-2.db", "automatic-3.db", "manual.db"} {
		path := filepath.Join(dir, name)
		if err := os.WriteFile(path, []byte(name), 0o600); err != nil {
			t.Fatal(err)
		}
		stamp := base.Add(time.Duration(index) * time.Minute)
		if err := os.Chtimes(path, stamp, stamp); err != nil {
			t.Fatal(err)
		}
	}
	if err := pruneAutomaticBackups(dir, 2); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"automatic-2.db", "automatic-3.db", "manual.db"} {
		if _, err := os.Stat(filepath.Join(dir, name)); err != nil {
			t.Fatalf("expected %s to remain: %v", name, err)
		}
	}
	if _, err := os.Stat(filepath.Join(dir, "automatic-1.db")); !os.IsNotExist(err) {
		t.Fatalf("oldest automatic backup should be removed, got %v", err)
	}
}

func TestPruneAutomaticBackupsDoesNothingBelowRetentionLimit(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "automatic-1.db")
	if err := os.WriteFile(path, []byte("backup"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := pruneAutomaticBackups(dir, 14); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("backup below retention limit should remain: %v", err)
	}
}
