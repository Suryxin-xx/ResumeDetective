package config

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

const DataDirEnv = "RESUME_DETECTIVE_V4_DATA_DIR"

type Paths struct {
	DataDir        string
	Database       string
	Workbook       string
	ConfigFile     string
	EnvFile        string
	SecretFile     string
	MigrationFile  string
	ResumesDir     string
	AttachmentsDir string
	BackupsDir     string
	UpdatesDir     string
	ReasonixDir    string
}

// ForSpace changes only user content paths. Credentials and service settings
// remain in the original portable data directory.
func ForSpace(base Paths, id string) Paths {
	if id == "default" {
		return base
	}
	dir := filepath.Join(base.DataDir, "spaces", id)
	p := base
	p.DataDir = dir
	p.Database = filepath.Join(dir, "resume_detective.db")
	p.Workbook = filepath.Join(dir, "投递追踪.xlsx")
	p.ResumesDir = filepath.Join(dir, "resumes")
	p.AttachmentsDir = filepath.Join(dir, "attachments")
	p.MigrationFile = filepath.Join(dir, "v3-migration.json")
	p.BackupsDir = filepath.Join(base.BackupsDir, "spaces", id)
	return p
}

func Resolve(dataDir string) (Paths, error) {
	if dataDir == "" {
		dataDir = os.Getenv(DataDirEnv)
	}
	if dataDir == "" {
		executable, err := os.Executable()
		if err != nil {
			return Paths{}, err
		}
		dataDir = filepath.Join(filepath.Dir(executable), "data")
	}
	abs, err := filepath.Abs(dataDir)
	if err != nil {
		return Paths{}, err
	}
	if filepath.Clean(abs) == filepath.VolumeName(abs)+string(filepath.Separator) {
		return Paths{}, errors.New("数据目录不能是磁盘根目录")
	}
	backupsDir := filepath.Join(abs, "backups")
	if strings.EqualFold(filepath.Base(abs), "data") {
		backupsDir = filepath.Join(filepath.Dir(abs), "backups")
	}
	p := Paths{
		DataDir:        abs,
		Database:       filepath.Join(abs, "resume_detective.db"),
		Workbook:       filepath.Join(abs, "秋招投递追踪.xlsx"),
		ConfigFile:     filepath.Join(abs, "config.json"),
		EnvFile:        filepath.Join(abs, ".env"),
		SecretFile:     filepath.Join(abs, "secret.json.enc"),
		MigrationFile:  filepath.Join(abs, "v3-migration.json"),
		ResumesDir:     filepath.Join(abs, "resumes"),
		AttachmentsDir: filepath.Join(abs, "attachments"),
		BackupsDir:     backupsDir,
		UpdatesDir:     filepath.Join(abs, "updates"),
		ReasonixDir:    filepath.Join(abs, "reasonix"),
	}
	for _, dir := range []string{p.DataDir, p.ResumesDir, p.AttachmentsDir, p.BackupsDir, p.UpdatesDir, p.ReasonixDir} {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return Paths{}, err
		}
	}
	probe := filepath.Join(p.DataDir, ".write-test")
	if err := os.WriteFile(probe, []byte("ok"), 0o600); err != nil {
		return Paths{}, errors.New("程序所在目录不可写；请将便携版解压到个人文件夹后再运行")
	}
	_ = os.Remove(probe)
	return p, nil
}
