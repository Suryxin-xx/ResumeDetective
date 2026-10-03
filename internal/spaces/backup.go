package spaces

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

type Manifest struct {
	Format    string            `json:"format"`
	Version   int               `json:"version"`
	SpaceID   string            `json:"spaceId"`
	Name      string            `json:"name"`
	CreatedAt string            `json:"createdAt"`
	SourceDir string            `json:"sourceDir"`
	Files     map[string]string `json:"files"`
}
type BackupStatus struct {
	CheckedAt       string `json:"checkedAt"`
	Success         bool   `json:"success"`
	FileName        string `json:"fileName"`
	Error           string `json:"error,omitempty"`
	LastSuccessAt   string `json:"lastSuccessAt,omitempty"`
	LastSuccessFile string `json:"lastSuccessFile,omitempty"`
}

func Status(p config.Paths) BackupStatus {
	var s BackupStatus
	b, err := os.ReadFile(filepath.Join(p.BackupsDir, "space-backup-status.json"))
	if err == nil {
		_ = json.Unmarshal(b, &s)
	}
	return s
}
func recordStatus(p config.Paths, name string, err error) {
	s := Status(p)
	s.CheckedAt, s.Success, s.FileName, s.Error = time.Now().Format(time.RFC3339), err == nil, name, ""
	if err != nil {
		s.Error = err.Error()
	} else {
		s.LastSuccessAt, s.LastSuccessFile = s.CheckedAt, name
	}
	b, _ := json.MarshalIndent(s, "", "  ")
	_ = os.MkdirAll(p.BackupsDir, 0700)
	f, e := os.CreateTemp(p.BackupsDir, ".status-*.tmp")
	if e != nil {
		return
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	_, e = f.Write(b)
	if e == nil {
		e = f.Sync()
	}
	_ = f.Close()
	if e == nil {
		_ = os.Rename(tmp, filepath.Join(p.BackupsDir, "space-backup-status.json"))
	}
}

// Backup must run under the caller's exclusive content gate so the database
// snapshot and managed files belong to the same application revision.
func Backup(ctx context.Context, st *store.Store, p config.Paths, space Space, prefix string) (name string, err error) {
	name = prefix + time.Now().Format("20060102-150405.000000000") + ".space.zip"
	defer func() { recordStatus(p, name, err) }()
	if err = os.MkdirAll(p.BackupsDir, 0700); err != nil {
		return "", err
	}
	stage, err := os.MkdirTemp(p.BackupsDir, ".space-backup-*")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(stage)
	dbPath := filepath.Join(stage, "resume_detective.db")
	if err = st.Backup(ctx, dbPath); err != nil {
		return "", err
	}
	refs, e := st.FileReferences(ctx)
	if e != nil {
		return "", e
	}
	for _, ref := range refs {
		rel, e := store.ManagedRelative(p.DataDir, ref)
		if e != nil {
			return "", e
		}
		info, e := os.Stat(filepath.Join(p.DataDir, rel))
		if e != nil || !info.Mode().IsRegular() {
			return "", fmt.Errorf("备份未完成：关联文件缺失 %s", rel)
		}
	}
	files := map[string]string{"resume_detective.db": dbPath}
	for _, dir := range []string{"resumes", "attachments"} {
		root := filepath.Join(p.DataDir, dir)
		if _, e := os.Stat(root); os.IsNotExist(e) {
			continue
		}
		err = filepath.WalkDir(root, func(path string, d fs.DirEntry, e error) error {
			if e != nil {
				return e
			}
			if d.Type()&os.ModeSymlink != 0 {
				return errors.New("受管文件目录包含符号链接，已停止备份")
			}
			if d.IsDir() {
				return nil
			}
			info, e := d.Info()
			if e != nil {
				return e
			}
			if !info.Mode().IsRegular() {
				return errors.New("备份只支持普通文件")
			}
			rel, e := filepath.Rel(p.DataDir, path)
			if e != nil {
				return e
			}
			files[filepath.ToSlash(rel)] = path
			return nil
		})
		if err != nil {
			return "", err
		}
	}
	manifest := Manifest{Format: "ResumeDetective-space", Version: 1, SpaceID: space.ID, Name: space.Name, CreatedAt: time.Now().Format(time.RFC3339), SourceDir: p.DataDir, Files: map[string]string{}}
	tmp := filepath.Join(stage, "bundle.zip")
	f, err := os.Create(tmp)
	if err != nil {
		return "", err
	}
	w := zip.NewWriter(f)
	for key, path := range files {
		if err = ctx.Err(); err != nil {
			break
		}
		var in *os.File
		in, err = os.Open(path)
		if err != nil {
			break
		}
		var out io.Writer
		out, err = w.Create(key)
		if err != nil {
			in.Close()
			break
		}
		h := sha256.New()
		_, err = io.Copy(io.MultiWriter(out, h), in)
		in.Close()
		if err != nil {
			break
		}
		manifest.Files[key] = hex.EncodeToString(h.Sum(nil))
	}
	if err == nil {
		var out io.Writer
		out, err = w.Create("space-manifest.json")
		if err == nil {
			err = json.NewEncoder(out).Encode(manifest)
		}
	}
	closeErr := w.Close()
	syncErr := f.Sync()
	fileErr := f.Close()
	if err != nil {
		return "", err
	}
	if closeErr != nil {
		return "", closeErr
	}
	if syncErr != nil {
		return "", syncErr
	}
	if fileErr != nil {
		return "", fileErr
	}
	if err = os.Rename(tmp, filepath.Join(p.BackupsDir, name)); err != nil {
		return "", err
	}
	return name, nil
}

func allowedEntry(name string) bool {
	if strings.Contains(name, "\\") || strings.Contains(name, ":") || strings.HasPrefix(name, "/") {
		return false
	}
	clean := filepath.ToSlash(filepath.Clean(name))
	if clean != name || strings.HasPrefix(clean, "../") {
		return false
	}
	return name == "resume_detective.db" || strings.HasPrefix(name, "resumes/") || strings.HasPrefix(name, "attachments/")
}

// Restore never replaces a live space; the caller supplies a fresh managed dir.
func Restore(ctx context.Context, archive string, p config.Paths) error {
	r, err := zip.OpenReader(archive)
	if err != nil {
		return errors.New("无法读取完整空间备份 ZIP")
	}
	defer r.Close()
	if len(r.File) > 10000 {
		return errors.New("备份文件数量超过安全上限")
	}
	var manifest Manifest
	seen := map[string]bool{}
	total := uint64(0)
	for _, f := range r.File {
		if f.Name == "space-manifest.json" {
			if seen[f.Name] || f.UncompressedSize64 > 1<<20 {
				return errors.New("备份清单无效")
			}
			seen[f.Name] = true
			in, e := f.Open()
			if e != nil {
				return e
			}
			e = json.NewDecoder(io.LimitReader(in, 1<<20)).Decode(&manifest)
			in.Close()
			if e != nil {
				return errors.New("备份清单损坏")
			}
		}
	}
	if manifest.Format != "ResumeDetective-space" || manifest.Version != 1 || manifest.SourceDir == "" || manifest.Files["resume_detective.db"] == "" {
		return errors.New("不是支持的完整空间备份；普通数据库请从数据目录导入")
	}
	for _, f := range r.File {
		if f.Name == "space-manifest.json" {
			continue
		}
		if !allowedEntry(f.Name) || seen[f.Name] || f.Mode()&os.ModeSymlink != 0 || f.FileInfo().IsDir() {
			return errors.New("备份包含重复、越界或不支持的文件路径")
		}
		seen[f.Name] = true
		if f.UncompressedSize64 > (2<<30)-total {
			return errors.New("备份解压大小超过 2GB 安全上限")
		}
		total += f.UncompressedSize64
		if err := ctx.Err(); err != nil {
			return err
		}
		if manifest.Files[f.Name] == "" {
			return errors.New("备份存在未登记文件")
		}
		path := filepath.Join(p.DataDir, filepath.FromSlash(f.Name))
		if err = os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			return err
		}
		out, e := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if e != nil {
			return e
		}
		in, e := f.Open()
		if e != nil {
			out.Close()
			return e
		}
		h := sha256.New()
		_, e = io.Copy(io.MultiWriter(out, h), io.LimitReader(in, int64(f.UncompressedSize64)+1))
		in.Close()
		closeErr := out.Close()
		if e != nil {
			return e
		}
		if closeErr != nil {
			return closeErr
		}
		if hex.EncodeToString(h.Sum(nil)) != manifest.Files[f.Name] {
			return errors.New("备份校验失败，没有覆盖原空间")
		}
	}
	for name := range manifest.Files {
		if !seen[name] {
			return errors.New("备份缺少清单中的文件")
		}
	}
	if err = store.InspectPortable(p.Database); err != nil {
		return err
	}
	st, err := store.Open(p.Database)
	if err != nil {
		return err
	}
	defer st.Close()
	return st.RebaseFiles(ctx, manifest.SourceDir, p.DataDir)
}

func ImportDirectory(ctx context.Context, source string, p config.Paths) error {
	abs, err := filepath.Abs(source)
	if err != nil {
		return err
	}
	if err = store.SnapshotPortable(ctx, filepath.Join(abs, "resume_detective.db"), p.Database); err != nil {
		return err
	}
	for _, dir := range []string{"resumes", "attachments"} {
		root := filepath.Join(abs, dir)
		if _, e := os.Stat(root); os.IsNotExist(e) {
			continue
		}
		err = filepath.WalkDir(root, func(path string, d fs.DirEntry, e error) error {
			if e != nil {
				return e
			}
			if d.Type()&os.ModeSymlink != 0 {
				return errors.New("导入目录不能包含符号链接")
			}
			rel, e := filepath.Rel(abs, path)
			if e != nil {
				return e
			}
			dst := filepath.Join(p.DataDir, rel)
			if d.IsDir() {
				return os.MkdirAll(dst, 0700)
			}
			info, e := d.Info()
			if e != nil {
				return e
			}
			if !info.Mode().IsRegular() {
				return errors.New("导入只支持普通文件")
			}
			in, e := os.Open(path)
			if e != nil {
				return e
			}
			defer in.Close()
			out, e := os.OpenFile(dst, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
			if e != nil {
				return e
			}
			_, e = io.Copy(out, in)
			closeErr := out.Close()
			if e != nil {
				return e
			}
			return closeErr
		})
		if err != nil {
			return err
		}
	}
	st, err := store.Open(p.Database)
	if err != nil {
		return err
	}
	defer st.Close()
	return st.RebaseFiles(ctx, abs, p.DataDir)
}
