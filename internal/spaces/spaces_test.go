package spaces

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

func fixture(t *testing.T) (*Manager, *store.Store, config.Paths) {
	t.Helper()
	p, err := config.Resolve(filepath.Join(t.TempDir(), "data"))
	if err != nil {
		t.Fatal(err)
	}
	m, err := Open(p, "秋招")
	if err != nil {
		t.Fatal(err)
	}
	st, selected, id, err := m.OpenSelected()
	if err != nil {
		t.Fatal(err)
	}
	if id != "default" || selected.Database != p.Database {
		t.Fatal("default paths changed")
	}
	if err = m.Commit(id); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { st.Close() })
	return m, st, p
}
func TestSpacesPreserveDefaultAndIsolateContent(t *testing.T) {
	m, original, p := fixture(t)
	ctx := context.Background()
	if _, err := original.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: "原始公司", PositionName: "秋招岗位"}); err != nil {
		t.Fatal(err)
	}
	space, err := m.Create("春招")
	if err != nil {
		t.Fatal(err)
	}
	target, err := m.Paths(space.ID)
	if err != nil {
		t.Fatal(err)
	}
	if target.Database == p.Database || target.Workbook == p.Workbook || target.ResumesDir == p.ResumesDir || target.BackupsDir == p.BackupsDir {
		t.Fatal("content paths not isolated")
	}
	if target.EnvFile != p.EnvFile || target.ConfigFile != p.ConfigFile || target.SecretFile != p.SecretFile {
		t.Fatal("credentials should stay global")
	}
	spring, err := store.Open(target.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer spring.Close()
	items, _ := spring.ListApplications(ctx)
	if len(items) != 0 {
		t.Fatal("new space was not empty")
	}
	id, err := spring.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: "春招公司", PositionName: "新岗位"})
	if err != nil || id != 1 {
		t.Fatalf("independent IDs: %d %v", id, err)
	}
	old, _ := original.ListApplications(ctx)
	if len(old) != 1 || old[0].CompanyName != "原始公司" {
		t.Fatal("original changed")
	}
	if err = m.PrepareSwitch(space.ID); err != nil {
		t.Fatal(err)
	}
	if m.Snapshot().ActiveID != "default" {
		t.Fatal("active changed before restart")
	}
	reopened, err := Open(p, "ignored")
	if err != nil {
		t.Fatal(err)
	}
	selected, _, active, err := reopened.OpenSelected()
	if err != nil {
		t.Fatal(err)
	}
	defer selected.Close()
	if active != space.ID {
		t.Fatal("pending switch not selected")
	}
	if err = reopened.Commit(active); err != nil {
		t.Fatal(err)
	}
	if err = reopened.Archive(active, true); err == nil {
		t.Fatal("archived active space")
	}
	if err = reopened.Commit("../../outside"); err == nil {
		t.Fatal("invalid commit accepted")
	}
}
func TestPendingFailureFallsBackWithoutRecreatingTarget(t *testing.T) {
	m, _, p := fixture(t)
	space, err := m.Create("坏目标")
	if err != nil {
		t.Fatal(err)
	}
	if err = m.PrepareSwitch(space.ID); err != nil {
		t.Fatal(err)
	}
	target, _ := m.Paths(space.ID)
	if err = os.WriteFile(target.Database, []byte("corrupt-test"), 0600); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(p, "")
	if err != nil {
		t.Fatal(err)
	}
	st, _, id, err := reopened.OpenSelected()
	if err != nil {
		t.Fatal(err)
	}
	st.Close()
	if id != "default" || reopened.Recovery() == "" || reopened.Snapshot().PendingID != "" {
		t.Fatal("did not fall back")
	}
	b, _ := os.ReadFile(target.Database)
	if string(b) != "corrupt-test" {
		t.Fatal("corrupt target was overwritten")
	}
}
func TestMissingActiveAndCorruptRegistryNeverReset(t *testing.T) {
	m, st, p := fixture(t)
	st.Close()
	if err := os.Remove(p.Database); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(p, "")
	if err != nil {
		t.Fatal(err)
	}
	if db, _, _, err := reopened.OpenSelected(); err == nil {
		db.Close()
		t.Fatal("missing active DB silently recreated")
	}
	if _, err := os.Stat(p.Database); !os.IsNotExist(err) {
		t.Fatal("missing DB created")
	}
	bad := []byte(`{"version":1,"activeId":"outside","items":[]}`)
	if err = os.WriteFile(filepath.Join(p.DataDir, "spaces.json"), bad, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(p, ""); err == nil {
		t.Fatal("invalid registry accepted")
	}
	after, _ := os.ReadFile(filepath.Join(p.DataDir, "spaces.json"))
	if string(after) != string(bad) {
		t.Fatal("registry overwritten")
	}
	_ = m
}
func TestFullBackupRestoreAndCredentialExclusion(t *testing.T) {
	m, st, p := fixture(t)
	ctx := context.Background()
	resume := filepath.Join(p.ResumesDir, "shared.pdf")
	if err := os.WriteFile(resume, []byte("virtual resume"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, company := range []string{"公司甲", "公司乙"} {
		if _, err := st.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: company, PositionName: "研发", ResumePath: resume}); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(p.EnvFile, []byte("TEST_FAKE_KEY=never_export"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p.ConfigFile, []byte("private config"), 0600); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(p.Database)
	beforeHash := sha256.Sum256(before)
	name, err := Backup(ctx, st, p, Space{ID: "default", Name: "秋招"}, "manual-")
	if err != nil {
		t.Fatal(err)
	}
	archive := filepath.Join(p.BackupsDir, name)
	r, err := zip.OpenReader(archive)
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]bool{}
	for _, f := range r.File {
		got[f.Name] = true
	}
	r.Close()
	if len(got) != 3 || !got["resume_detective.db"] || !got["resumes/shared.pdf"] || !got["space-manifest.json"] {
		t.Fatalf("unexpected archive: %v", got)
	}
	recovered, err := m.Install("恢复副本", func(target config.Paths) error { return Restore(ctx, archive, target) })
	if err != nil {
		t.Fatal(err)
	}
	target, _ := m.Paths(recovered.ID)
	copy, err := store.Open(target.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer copy.Close()
	items, err := copy.ListApplications(ctx)
	if err != nil || len(items) != 2 {
		t.Fatalf("restore records: %v %v", items, err)
	}
	expected := filepath.Join(target.ResumesDir, "shared.pdf")
	if items[0].ResumePath != expected || items[1].ResumePath != expected {
		t.Fatal("shared resume not rebased")
	}
	original, _ := st.ListApplications(ctx)
	if original[0].ResumePath != resume {
		t.Fatal("original binding changed")
	}
	after, _ := os.ReadFile(p.Database)
	if sha256.Sum256(after) != beforeHash {
		t.Fatal("backup/restore modified source DB")
	}
	status := Status(p)
	if !status.Success || status.LastSuccessFile != name {
		t.Fatal("backup success not recorded")
	}
	if err := os.Remove(resume); err != nil {
		t.Fatal(err)
	}
	if _, err := Backup(ctx, st, p, Space{ID: "default"}, "manual-"); err == nil {
		t.Fatal("missing reference backup succeeded")
	}
	status = Status(p)
	if status.Success || status.Error == "" || status.LastSuccessFile != name {
		t.Fatal("failure hid last successful backup")
	}
}
func TestDirectoryImportIsReadOnlyAndIndependent(t *testing.T) {
	m, st, p := fixture(t)
	ctx := context.Background()
	if _, err := st.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: "导入源", PositionName: "岗位"}); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(p.Database)
	imported, err := m.Install("副本", func(target config.Paths) error { return ImportDirectory(ctx, p.DataDir, target) })
	if err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(p.Database)
	if sha256.Sum256(after) != sha256.Sum256(before) {
		t.Fatal("import modified source")
	}
	target, _ := m.Paths(imported.ID)
	copy, err := store.Open(target.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer copy.Close()
	items, _ := copy.ListApplications(ctx)
	if len(items) != 1 || items[0].CompanyName != "导入源" {
		t.Fatal("source records lost")
	}
}
func TestFailedInstallNotPublishedAndOwnDirectoriesCleaned(t *testing.T) {
	m, _, _ := fixture(t)
	var target config.Paths
	_, err := m.Install("失败导入", func(p config.Paths) error { target = p; return errors.New("test failure") })
	if err == nil || len(m.Snapshot().Items) != 1 {
		t.Fatal("failed import published")
	}
	for _, dir := range []string{target.DataDir, target.BackupsDir} {
		if _, err := os.Stat(dir); !os.IsNotExist(err) {
			t.Fatal("failed new space was not cleaned")
		}
	}
}
func TestRestoreRejectsUntrustedArchiveAndUnsupportedPaths(t *testing.T) {
	m, _, p := fixture(t)
	for _, name := range []string{"../escape", "resumes/../../escape", "/absolute", "resumes\\evil", "C:/escape", "config.json", "resumes/../data"} {
		if allowedEntry(name) {
			t.Fatalf("accepted %q", name)
		}
	}
	archive := filepath.Join(t.TempDir(), "untrusted.zip")
	out, err := os.Create(archive)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(out)
	entry, _ := w.Create("space-manifest.json")
	entry.Write([]byte(`{"format":"ResumeDetective-space","version":1,"sourceDir":"old","files":{"resume_detective.db":"fake"}}`))
	entry, _ = w.Create("../escape")
	entry.Write([]byte("bad"))
	w.Close()
	out.Close()
	_, err = m.Install("恶意包", func(target config.Paths) error { return Restore(context.Background(), archive, target) })
	if err == nil || len(m.Snapshot().Items) != 1 {
		t.Fatal("malicious archive accepted")
	}
	if _, err := os.Stat(filepath.Join(p.DataDir, "spaces", "escape")); !os.IsNotExist(err) {
		t.Fatal("escape file written")
	}
}
func TestArchiveIsReversibleWithoutRemovingData(t *testing.T) {
	m, _, _ := fixture(t)
	space, err := m.Create("归档")
	if err != nil {
		t.Fatal(err)
	}
	path, _ := m.Paths(space.ID)
	if err = m.Archive(space.ID, true); err != nil {
		t.Fatal(err)
	}
	if _, err = m.Paths(space.ID); err == nil {
		t.Fatal("archived space selectable")
	}
	if _, err = os.Stat(path.Database); err != nil {
		t.Fatal("archive removed data")
	}
	if err = m.Archive(space.ID, false); err != nil {
		t.Fatal(err)
	}
	if _, err = m.Paths(space.ID); err != nil {
		t.Fatal(err)
	}
	if err = m.Rename(space.ID, strings.Repeat("字", 61)); err == nil {
		t.Fatal("oversized name accepted")
	}
}

func TestRestoreDetectsChangedPayloadWithoutTouchingOriginal(t *testing.T) {
	m, st, p := fixture(t)
	ctx := context.Background()
	resume := filepath.Join(p.ResumesDir, "test.pdf")
	if err := os.WriteFile(resume, []byte("original"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := st.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: "校验公司", PositionName: "岗位", ResumePath: resume}); err != nil {
		t.Fatal(err)
	}
	name, err := Backup(ctx, st, p, Space{ID: "default"}, "manual-")
	if err != nil {
		t.Fatal(err)
	}
	r, err := zip.OpenReader(filepath.Join(p.BackupsDir, name))
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	tampered := filepath.Join(t.TempDir(), "tampered.zip")
	out, err := os.Create(tampered)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(out)
	for _, file := range r.File {
		entry, err := w.Create(file.Name)
		if err != nil {
			t.Fatal(err)
		}
		if file.Name == "resumes/test.pdf" {
			entry.Write([]byte("changed"))
			continue
		}
		in, err := file.Open()
		if err != nil {
			t.Fatal(err)
		}
		_, err = io.Copy(entry, in)
		in.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
	if err = w.Close(); err != nil {
		t.Fatal(err)
	}
	out.Close()
	_, err = m.Install("坏备份", func(target config.Paths) error { return Restore(ctx, tampered, target) })
	if err == nil || !strings.Contains(err.Error(), "校验") || len(m.Snapshot().Items) != 1 {
		t.Fatalf("tampered package accepted: %v", err)
	}
	b, _ := os.ReadFile(resume)
	if string(b) != "original" {
		t.Fatal("original file modified")
	}
	items, _ := st.ListApplications(ctx)
	if len(items) != 1 || items[0].ResumePath != resume {
		t.Fatal("original record modified")
	}
}
