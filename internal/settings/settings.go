package settings

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	DefaultPort          = 8765
	DefaultWorkspaceName = "秋招工作台"
)

type AIConfig struct {
	Mode                 string `json:"mode"`
	BaseURL              string `json:"baseUrl"`
	Model                string `json:"model"`
	Thinking             bool   `json:"thinking"`
	ReasonixPath         string `json:"reasonixPath"`
	CheckReasonixUpdates bool   `json:"checkReasonixUpdates"`
}

type Config struct {
	Port                int      `json:"port"`
	WorkspaceName       string   `json:"workspaceName"`
	Theme               string   `json:"theme"`
	OpenBrowserOnStart  bool     `json:"openBrowserOnStart"`
	StartAtLogin        bool     `json:"startAtLogin"`
	CheckUpdatesOnStart bool     `json:"checkUpdatesOnStart"`
	AutoBackupEnabled   bool     `json:"autoBackupEnabled"`
	AutoBackupHours     int      `json:"autoBackupHours"`
	BackupRetention     int      `json:"backupRetention"`
	AI                  AIConfig `json:"ai"`
}

type Manager struct {
	mu      sync.RWMutex
	path    string
	envPath string
	value   Config
}

func Defaults() Config {
	return Config{
		Port:                DefaultPort,
		WorkspaceName:       DefaultWorkspaceName,
		Theme:               "bright",
		OpenBrowserOnStart:  true,
		CheckUpdatesOnStart: true,
		AutoBackupEnabled:   true,
		AutoBackupHours:     24,
		BackupRetention:     14,
		AI: AIConfig{
			Mode:                 "direct",
			BaseURL:              "https://api.deepseek.com",
			Model:                "deepseek-v4-flash",
			Thinking:             false,
			CheckReasonixUpdates: true,
		},
	}
}

func Open(path, envPath string) (*Manager, error) {
	m := &Manager{path: path, envPath: envPath, value: Defaults()}
	if raw, err := os.ReadFile(path); err == nil {
		if err := json.Unmarshal(raw, &m.value); err != nil {
			return nil, errors.New("配置文件格式不正确")
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	m.value.normalize()
	if err := loadEnv(envPath); err != nil {
		return nil, err
	}
	return m, nil
}

func (m *Manager) Get() Config {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.value
}

func (m *Manager) Save(next Config) error {
	next.normalize()
	raw, err := json.MarshalIndent(next, "", "  ")
	if err != nil {
		return err
	}
	if err := atomicWrite(m.path, append(raw, '\n'), 0o600); err != nil {
		return err
	}
	m.mu.Lock()
	m.value = next
	m.mu.Unlock()
	return nil
}

func (m *Manager) HasAPIKey() bool {
	return strings.TrimSpace(os.Getenv("DEEPSEEK_API_KEY")) != ""
}

func (m *Manager) SaveAPIKey(key string) error {
	key = strings.TrimSpace(key)
	if key == "" {
		return errors.New("API Key 不能为空")
	}
	if strings.ContainsAny(key, "\r\n") {
		return errors.New("API Key 格式不正确")
	}
	if err := upsertEnv(m.envPath, "DEEPSEEK_API_KEY", key); err != nil {
		return err
	}
	return os.Setenv("DEEPSEEK_API_KEY", key)
}

func (m *Manager) DeleteAPIKey() error {
	if err := upsertEnv(m.envPath, "DEEPSEEK_API_KEY", ""); err != nil {
		return err
	}
	return os.Unsetenv("DEEPSEEK_API_KEY")
}

func (c *Config) normalize() {
	if c.Port < 1024 || c.Port > 65535 {
		c.Port = DefaultPort
	}
	c.WorkspaceName = strings.TrimSpace(c.WorkspaceName)
	if c.WorkspaceName == "" {
		c.WorkspaceName = DefaultWorkspaceName
	}
	if c.Theme != "soft" {
		c.Theme = "bright"
	}
	if c.AutoBackupHours < 1 || c.AutoBackupHours > 24*90 {
		c.AutoBackupHours = 24
	}
	if c.BackupRetention < 1 || c.BackupRetention > 365 {
		c.BackupRetention = 14
	}
	c.AI.Mode = strings.ToLower(strings.TrimSpace(c.AI.Mode))
	if c.AI.Mode != "reasonix" {
		c.AI.Mode = "direct"
	}
	c.AI.BaseURL = strings.TrimRight(strings.TrimSpace(c.AI.BaseURL), "/")
	if c.AI.BaseURL == "" {
		c.AI.BaseURL = "https://api.deepseek.com"
	}
	c.AI.Model = strings.TrimSpace(c.AI.Model)
	if c.AI.Model == "" || c.AI.Model == "deepseek-chat" || c.AI.Model == "deepseek-reasoner" {
		c.AI.Model = "deepseek-v4-flash"
	}
}

func loadEnv(path string) error {
	raw, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "export "))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok || strings.TrimSpace(key) == "" {
			continue
		}
		key, value = strings.TrimSpace(key), strings.Trim(strings.TrimSpace(value), `"'`)
		if os.Getenv(key) == "" {
			_ = os.Setenv(key, value)
		}
	}
	return nil
}

func upsertEnv(path, key, value string) error {
	lines := []string{"# ResumeDetective 本地密钥。该文件不得提交到 Git。"}
	if raw, err := os.ReadFile(path); err == nil {
		lines = strings.Split(strings.TrimRight(string(raw), "\r\n"), "\n")
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	replacement := key + "=" + value
	found := false
	for index, line := range lines {
		candidate := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "export "))
		if current, _, ok := strings.Cut(candidate, "="); ok && strings.TrimSpace(current) == key {
			lines[index] = replacement
			found = true
		}
	}
	if !found {
		lines = append(lines, replacement)
	}
	return atomicWrite(path, []byte(strings.Join(lines, "\n")+"\n"), 0o600)
}

func atomicWrite(path string, data []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	temp, err := os.CreateTemp(filepath.Dir(path), ".settings-*.tmp")
	if err != nil {
		return err
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	if err := temp.Chmod(mode); err != nil {
		temp.Close()
		return err
	}
	if _, err := temp.Write(data); err != nil {
		temp.Close()
		return err
	}
	if err := temp.Sync(); err != nil {
		temp.Close()
		return err
	}
	if err := temp.Close(); err != nil {
		return err
	}
	_ = os.Remove(path + ".previous")
	if _, err := os.Stat(path); err == nil {
		if err := os.Rename(path, path+".previous"); err != nil {
			return err
		}
	}
	if err := os.Rename(tempPath, path); err != nil {
		_ = os.Rename(path+".previous", path)
		return err
	}
	_ = os.Remove(path + ".previous")
	return nil
}

func ShouldRunBackup(last time.Time, cfg Config, now time.Time) bool {
	return cfg.AutoBackupEnabled && (last.IsZero() || now.Sub(last) >= time.Duration(cfg.AutoBackupHours)*time.Hour)
}

func ParseBoolEnv(name string, fallback bool) bool {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.ParseBool(raw)
	return err == nil && value
}
