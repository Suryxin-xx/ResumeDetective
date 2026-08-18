package httpapi

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

func TestRenderResumeName(t *testing.T) {
	app := store.Application{CompanyName: `示例/科技`, PositionName: `后端:工程师`, Category: "研发", AppliedAt: "2026-08-18"}
	got := renderResumeName("{company}-{position}-{category}-{date}", app, time.Time{})
	if got != "示例-科技-后端-工程师-研发-2026-08-18" {
		t.Fatalf("unexpected resume name %q", got)
	}
}

func TestAvailableResumePathAddsSuffix(t *testing.T) {
	dir := t.TempDir()
	first := filepath.Join(dir, "示例-后端.pdf")
	if err := os.WriteFile(first, []byte("pdf"), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := availableResumePath(dir, "示例-后端", ".pdf", "")
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(got) != "示例-后端-2.pdf" {
		t.Fatalf("unexpected path %q", got)
	}
}

func TestPathInsideDirectory(t *testing.T) {
	dir := t.TempDir()
	if !pathInsideDirectory(dir, filepath.Join(dir, "resume.pdf")) {
		t.Fatal("expected path inside resume directory")
	}
	if pathInsideDirectory(dir, filepath.Join(filepath.Dir(dir), "private.pdf")) {
		t.Fatal("external file must not be accepted")
	}
}
