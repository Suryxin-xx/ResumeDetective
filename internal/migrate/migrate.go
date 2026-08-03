package migrate

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
	_ "github.com/mattn/go-sqlite3"
)

const sourceEnv = "RESUME_DETECTIVE_V3_DATA_DIR"

type Report struct {
	Imported   bool   `json:"imported"`
	SourceDir  string `json:"sourceDir,omitempty"`
	Reason     string `json:"reason"`
	ImportedAt string `json:"importedAt,omitempty"`
}

type Status struct {
	Available    bool   `json:"available"`
	SourceDir    string `json:"sourceDir,omitempty"`
	Applications int    `json:"applications"`
	Reason       string `json:"reason"`
}

func Inspect(sourceDir string) Status {
	if !validSource(sourceDir) {
		return Status{Reason: "未发现可导入的 v3 数据"}
	}
	db, err := sql.Open("sqlite3", "file:"+filepath.ToSlash(filepath.Join(sourceDir, "data.db"))+"?mode=ro")
	if err != nil {
		return Status{SourceDir: sourceDir, Reason: "无法读取 v3 数据库"}
	}
	defer db.Close()
	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM applications").Scan(&count); err != nil {
		return Status{SourceDir: sourceDir, Reason: "v3 数据库结构不兼容"}
	}
	return Status{Available: true, SourceDir: sourceDir, Applications: count, Reason: "可以复制到独立的 v4 数据库"}
}

func ImportIntoStore(ctx context.Context, st *store.Store, paths config.Paths, sourceDir string) (Report, error) {
	status := Inspect(sourceDir)
	if !status.Available {
		return Report{Reason: status.Reason}, errors.New(status.Reason)
	}
	empty, err := st.BusinessDataEmpty(ctx)
	if err != nil {
		return Report{}, err
	}
	if !empty {
		return Report{SourceDir: sourceDir, Reason: "v4 已有业务数据，未导入"}, errors.New("v4 已有业务数据；请使用空白数据目录或先导出当前记录")
	}
	stamp := time.Now().Format("20060102-150405")
	if err := st.Backup(ctx, filepath.Join(paths.BackupsDir, "before-v3-import-"+stamp+".db")); err != nil {
		return Report{}, err
	}
	tempDB := filepath.Join(paths.DataDir, "v3-import-"+stamp+".db")
	defer os.Remove(tempDB)
	if err := snapshotDatabase(ctx, filepath.Join(sourceDir, "data.db"), tempDB); err != nil {
		return Report{}, err
	}
	if err := normalizeManagedPaths(tempDB, sourceDir); err != nil {
		return Report{}, err
	}
	for _, pair := range [][2]string{{"Resumes", paths.ResumesDir}, {"Attachments", paths.AttachmentsDir}} {
		if err := copyTreeMissing(filepath.Join(sourceDir, pair[0]), pair[1]); err != nil {
			return Report{}, err
		}
	}
	for _, pair := range [][2]string{{"config.json", paths.ConfigFile}, {"secret.json.enc", paths.SecretFile}, {"秋招投递追踪.xlsx", filepath.Join(paths.DataDir, "秋招投递追踪.xlsx")}} {
		if err := copyFileIfMissing(filepath.Join(sourceDir, pair[0]), pair[1]); err != nil {
			return Report{}, err
		}
	}
	if err := st.ImportV3Snapshot(ctx, tempDB); err != nil {
		return Report{}, err
	}
	report := Report{Imported: true, SourceDir: sourceDir, Reason: "已复制 v3 数据，原目录保持不变", ImportedAt: time.Now().Format(time.RFC3339)}
	payload, _ := json.MarshalIndent(report, "", "  ")
	if err := os.WriteFile(paths.MigrationFile, payload, 0o600); err != nil {
		return Report{}, err
	}
	return report, nil
}

func Discover(explicit string) string {
	for _, candidate := range []string{explicit, os.Getenv(sourceEnv)} {
		if validSource(candidate) {
			return filepath.Clean(candidate)
		}
	}
	starts := make([]string, 0, 2)
	if cwd, err := os.Getwd(); err == nil {
		starts = append(starts, cwd)
	}
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}
	seen := map[string]bool{}
	for _, start := range starts {
		dir := filepath.Clean(start)
		for depth := 0; depth < 7; depth++ {
			if seen[dir] {
				break
			}
			seen[dir] = true
			if configured := configuredDataDir(filepath.Join(dir, ".resumedetective.local.json")); validSource(configured) {
				return configured
			}
			if validSource(filepath.Join(dir, "data")) {
				return filepath.Join(dir, "data")
			}
			if validSource(filepath.Join(filepath.Dir(dir), "ResumeDetective-LocalData")) {
				return filepath.Join(filepath.Dir(dir), "ResumeDetective-LocalData")
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return ""
}

func ImportIfEmpty(ctx context.Context, paths config.Paths, sourceDir string) (Report, error) {
	if sourceDir == "" {
		return Report{Reason: "未发现 v3 数据目录"}, nil
	}
	sourceDir, _ = filepath.Abs(sourceDir)
	if samePath(sourceDir, paths.DataDir) {
		return Report{Reason: "v3 与 v4 数据目录相同，已拒绝共用"}, nil
	}
	empty, err := targetIsEmpty(paths.Database)
	if err != nil {
		return Report{}, err
	}
	if !empty {
		return Report{SourceDir: sourceDir, Reason: "v4 已有业务数据，未自动覆盖"}, nil
	}
	sourceDB := filepath.Join(sourceDir, "data.db")
	if err := validateSource(sourceDB); err != nil {
		return Report{}, err
	}
	stamp := time.Now().Format("20060102-150405")
	tempDB := paths.Database + ".importing"
	_ = os.Remove(tempDB)
	if err := snapshotDatabase(ctx, sourceDB, tempDB); err != nil {
		return Report{}, err
	}
	if err := normalizeManagedPaths(tempDB, sourceDir); err != nil {
		_ = os.Remove(tempDB)
		return Report{}, err
	}
	if err := preserveCurrentDatabase(paths, stamp); err != nil {
		_ = os.Remove(tempDB)
		return Report{}, err
	}
	if err := os.Rename(tempDB, paths.Database); err != nil {
		return Report{}, err
	}
	for _, pair := range [][2]string{{"Resumes", paths.ResumesDir}, {"Attachments", paths.AttachmentsDir}} {
		if err := copyTreeMissing(filepath.Join(sourceDir, pair[0]), pair[1]); err != nil {
			return Report{}, err
		}
	}
	for _, pair := range [][2]string{{"config.json", paths.ConfigFile}, {"secret.json.enc", paths.SecretFile}, {"秋招投递追踪.xlsx", filepath.Join(paths.DataDir, "秋招投递追踪.xlsx")}} {
		if err := copyFileIfMissing(filepath.Join(sourceDir, pair[0]), pair[1]); err != nil {
			return Report{}, err
		}
	}
	report := Report{Imported: true, SourceDir: sourceDir, Reason: "已复制 v3 数据，原目录保持不变", ImportedAt: time.Now().Format(time.RFC3339)}
	payload, _ := json.MarshalIndent(report, "", "  ")
	if err := os.WriteFile(paths.MigrationFile, payload, 0o600); err != nil {
		return Report{}, err
	}
	return report, nil
}

func targetIsEmpty(database string) (bool, error) {
	if info, err := os.Stat(database); errors.Is(err, os.ErrNotExist) || (err == nil && info.Size() == 0) {
		return true, nil
	} else if err != nil {
		return false, err
	}
	db, err := sql.Open("sqlite3", "file:"+filepath.ToSlash(database)+"?mode=ro")
	if err != nil {
		return false, err
	}
	defer db.Close()
	var hasApplications int
	if err := db.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='applications'").Scan(&hasApplications); err != nil {
		return false, err
	}
	if hasApplications == 0 {
		return true, nil
	}
	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM applications").Scan(&count); err != nil {
		return false, err
	}
	return count == 0, nil
}

func validateSource(database string) error {
	db, err := sql.Open("sqlite3", "file:"+filepath.ToSlash(database)+"?mode=ro")
	if err != nil {
		return err
	}
	defer db.Close()
	var integrity string
	if err := db.QueryRow("PRAGMA integrity_check").Scan(&integrity); err != nil {
		return err
	}
	if integrity != "ok" {
		return fmt.Errorf("v3 数据库完整性检查失败: %s", integrity)
	}
	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		return err
	}
	if version > store.SchemaVersion {
		return fmt.Errorf("v3 数据库版本 %d 高于当前支持版本", version)
	}
	for _, table := range []string{"resumes", "applications", "materials", "profile", "job_targets", "application_attachments", "job_tasks", "interviews"} {
		var count int
		if err := db.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&count); err != nil || count != 1 {
			return fmt.Errorf("v3 数据库缺少表 %s", table)
		}
	}
	return nil
}

func snapshotDatabase(ctx context.Context, source, destination string) error {
	db, err := sql.Open("sqlite3", "file:"+filepath.ToSlash(source)+"?mode=ro")
	if err != nil {
		return err
	}
	defer db.Close()
	if _, err := db.ExecContext(ctx, "VACUUM INTO ?", destination); err != nil {
		return fmt.Errorf("复制 v3 数据库: %w", err)
	}
	return validateSource(destination)
}

func normalizeManagedPaths(database, sourceDir string) error {
	db, err := sql.Open("sqlite3", database)
	if err != nil {
		return err
	}
	defer db.Close()
	rows, err := db.Query("SELECT id,file_path FROM resumes WHERE file_path<>''")
	if err != nil {
		return err
	}
	type entry struct {
		id    int64
		value string
	}
	entries := []entry{}
	for rows.Next() {
		var item entry
		if err := rows.Scan(&item.id, &item.value); err != nil {
			rows.Close()
			return err
		}
		entries = append(entries, item)
	}
	rows.Close()
	for _, item := range entries {
		if relative, ok := relativeTo(item.value, sourceDir); ok {
			if _, err := db.Exec("UPDATE resumes SET file_path=? WHERE id=?", filepath.ToSlash(filepath.Join("data", relative)), item.id); err != nil {
				return err
			}
		}
	}
	return nil
}

func preserveCurrentDatabase(paths config.Paths, stamp string) error {
	for _, suffix := range []string{"", "-wal", "-shm"} {
		source := paths.Database + suffix
		if _, err := os.Stat(source); errors.Is(err, os.ErrNotExist) {
			continue
		} else if err != nil {
			return err
		}
		name := fmt.Sprintf("pre-v3-import-%s%s", stamp, suffix)
		if suffix == "" {
			name += ".db"
		}
		if err := os.Rename(source, filepath.Join(paths.BackupsDir, name)); err != nil {
			return err
		}
	}
	return nil
}

func configuredDataDir(path string) string {
	raw, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var value struct {
		DataDir string `json:"data_dir"`
	}
	if json.Unmarshal(raw, &value) != nil {
		return ""
	}
	return strings.TrimSpace(os.ExpandEnv(value.DataDir))
}

func validSource(dir string) bool {
	if strings.TrimSpace(dir) == "" {
		return false
	}
	info, err := os.Stat(filepath.Join(dir, "data.db"))
	return err == nil && info.Mode().IsRegular()
}
func samePath(a, b string) bool {
	aa, _ := filepath.Abs(a)
	bb, _ := filepath.Abs(b)
	return strings.EqualFold(filepath.Clean(aa), filepath.Clean(bb))
}

func relativeTo(stored, sourceDir string) (string, bool) {
	clean := filepath.FromSlash(stored)
	if filepath.IsAbs(clean) {
		rel, err := filepath.Rel(sourceDir, clean)
		return rel, err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
	}
	parts := strings.Split(filepath.ToSlash(stored), "/")
	if len(parts) > 1 && strings.EqualFold(parts[0], "data") {
		return filepath.FromSlash(strings.Join(parts[1:], "/")), true
	}
	return "", false
}

func copyTreeMissing(source, destination string) error {
	entries, err := os.ReadDir(source)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if err := os.MkdirAll(destination, 0o700); err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.Type()&os.ModeSymlink != 0 {
			continue
		}
		src := filepath.Join(source, entry.Name())
		dst := filepath.Join(destination, entry.Name())
		if entry.IsDir() {
			if err := copyTreeMissing(src, dst); err != nil {
				return err
			}
		} else if err := copyFileIfMissing(src, dst); err != nil {
			return err
		}
	}
	return nil
}

func copyFileIfMissing(source, destination string) error {
	src, err := os.Open(source)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	defer src.Close()
	if _, err := os.Stat(destination); err == nil {
		return nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
		return err
	}
	temp, err := os.CreateTemp(filepath.Dir(destination), ".copying-")
	if err != nil {
		return err
	}
	tempName := temp.Name()
	defer os.Remove(tempName)
	if _, err = io.Copy(temp, src); err != nil {
		temp.Close()
		return err
	}
	if err = temp.Sync(); err != nil {
		temp.Close()
		return err
	}
	if err = temp.Close(); err != nil {
		return err
	}
	return os.Rename(tempName, destination)
}
