// Package spaces manages portable, isolated job-search spaces. It never moves
// the legacy default data directory and never stores API credentials.
package spaces

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

type Space struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	Archived  bool   `json:"archived"`
	CreatedAt string `json:"createdAt"`
}
type Registry struct {
	Version   int     `json:"version"`
	ActiveID  string  `json:"activeId"`
	PendingID string  `json:"pendingId,omitempty"`
	Items     []Space `json:"items"`
}
type Manager struct {
	mu       sync.Mutex
	base     config.Paths
	registry Registry
	recovery string
	fresh    bool
}

var validID = regexp.MustCompile(`^(default|s-[a-f0-9]{16})$`)

func NewID() string {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return "s-" + hex.EncodeToString(b)
}
func Open(base config.Paths, name string) (*Manager, error) {
	m := &Manager{base: base}
	b, err := os.ReadFile(filepath.Join(base.DataDir, "spaces.json"))
	if os.IsNotExist(err) {
		m.fresh = true
		if strings.TrimSpace(name) == "" {
			name = "默认空间"
		}
		m.registry = Registry{Version: 1, ActiveID: "default", Items: []Space{{ID: "default", Name: name, CreatedAt: time.Now().Format(time.RFC3339)}}}
		return m, m.persist()
	}
	if err != nil {
		return nil, err
	}
	if err = json.Unmarshal(b, &m.registry); err != nil {
		return nil, errors.New("空间索引损坏；已停止启动，没有重建或清空数据")
	}
	if m.registry.Version != 1 {
		return nil, errors.New("空间索引版本不受支持")
	}
	seen := map[string]bool{}
	for _, s := range m.registry.Items {
		if !validID.MatchString(s.ID) || seen[s.ID] || strings.TrimSpace(s.Name) == "" {
			return nil, errors.New("空间索引内容无效")
		}
		seen[s.ID] = true
	}
	if !seen["default"] || !seen[m.registry.ActiveID] || (m.registry.PendingID != "" && !seen[m.registry.PendingID]) {
		return nil, errors.New("当前空间索引无效，未修改数据")
	}
	return m, nil
}
func (m *Manager) persist() error {
	b, err := json.MarshalIndent(m.registry, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(m.base.DataDir, ".spaces-*.tmp")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if _, err = f.Write(b); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(name, filepath.Join(m.base.DataDir, "spaces.json"))
}
func (m *Manager) Snapshot() Registry {
	m.mu.Lock()
	defer m.mu.Unlock()
	r := m.registry
	r.Items = append([]Space(nil), r.Items...)
	return r
}
func (m *Manager) Paths(id string) (config.Paths, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, s := range m.registry.Items {
		if s.ID == id && !s.Archived {
			return config.ForSpace(m.base, id), nil
		}
	}
	return config.Paths{}, errors.New("空间不存在或已归档")
}
func (m *Manager) Selection() (string, string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	id := m.registry.ActiveID
	if m.registry.PendingID != "" {
		id = m.registry.PendingID
	}
	return id, m.registry.ActiveID
}
func (m *Manager) Commit(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	valid := false
	for _, s := range m.registry.Items {
		if s.ID == id && !s.Archived {
			valid = true
		}
	}
	if !valid {
		return errors.New("不能确认不存在或已归档的空间")
	}
	old := m.registry
	m.registry.ActiveID = id
	m.registry.PendingID = ""
	if err := m.persist(); err != nil {
		m.registry = old
		return err
	}
	return nil
}
func (m *Manager) Recover(reason string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.recovery = reason
	m.registry.PendingID = ""
	return m.persist()
}
func (m *Manager) Recovery() string { m.mu.Lock(); defer m.mu.Unlock(); return m.recovery }

// OpenSelected does not recreate a missing registered database. A pending
// selection that fails validation falls back to the previous active space.
func (m *Manager) OpenSelected() (*store.Store, config.Paths, string, error) {
	id, previous := m.Selection()
	open := func(id string) (*store.Store, config.Paths, error) {
		p, err := m.Paths(id)
		if err != nil {
			return nil, p, err
		}
		_, statErr := os.Stat(p.Database)
		if !(m.fresh && id == "default" && os.IsNotExist(statErr)) {
			if err = store.InspectPortable(p.Database); err != nil {
				return nil, p, err
			}
		}
		st, err := store.Open(p.Database)
		return st, p, err
	}
	st, p, err := open(id)
	if err != nil && id != previous {
		if e := m.Recover("目标空间打开失败，已回到原空间：" + err.Error()); e != nil {
			return nil, p, id, e
		}
		id = previous
		st, p, err = open(id)
	}
	return st, p, id, err
}
func (m *Manager) PrepareSwitch(id string) error {
	p, err := m.Paths(id)
	if err != nil {
		return err
	}
	if err = store.InspectPortable(p.Database); err != nil {
		return err
	}
	// Upgrade only the selected managed target, with Store.Open's own snapshot.
	st, err := store.Open(p.Database)
	if err != nil {
		return err
	}
	if err = st.Close(); err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.registry.PendingID != "" {
		return errors.New("已有空间切换正在进行")
	}
	m.registry.PendingID = id
	if err = m.persist(); err != nil {
		m.registry.PendingID = ""
		return err
	}
	return nil
}
func validName(name string) (string, error) {
	name = strings.TrimSpace(name)
	if name == "" || len([]rune(name)) > 60 {
		return "", errors.New("空间名称须为 1–60 个字符")
	}
	return name, nil
}
func (m *Manager) Create(name string) (Space, error) {
	return m.Install(name, func(p config.Paths) error {
		st, err := store.Open(p.Database)
		if err != nil {
			return err
		}
		return st.Close()
	})
}

// Install publishes the registry entry only after a complete validated import.
func (m *Manager) Install(name string, prepare func(config.Paths) error) (Space, error) {
	name, err := validName(name)
	if err != nil {
		return Space{}, err
	}
	id := NewID()
	p := config.ForSpace(m.base, id)
	if err = os.MkdirAll(filepath.Dir(p.DataDir), 0700); err != nil {
		return Space{}, err
	}
	// Only rollback directories created by this operation, never an existing one.
	if err = os.Mkdir(p.DataDir, 0700); err != nil {
		return Space{}, err
	}
	backupCreated := false
	defer func() {
		if err != nil {
			os.RemoveAll(p.DataDir)
			if backupCreated {
				os.RemoveAll(p.BackupsDir)
			}
		}
	}()
	if err = os.MkdirAll(filepath.Dir(p.BackupsDir), 0700); err != nil {
		return Space{}, err
	}
	if err = os.Mkdir(p.BackupsDir, 0700); err != nil {
		return Space{}, err
	}
	backupCreated = true
	for _, dir := range []string{p.ResumesDir, p.AttachmentsDir} {
		if err = os.MkdirAll(dir, 0700); err != nil {
			return Space{}, err
		}
	}
	if err = prepare(p); err != nil {
		return Space{}, err
	}
	s := Space{ID: id, Name: name, CreatedAt: time.Now().Format(time.RFC3339)}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.registry.Items = append(m.registry.Items, s)
	if err = m.persist(); err != nil {
		m.registry.Items = m.registry.Items[:len(m.registry.Items)-1]
		return Space{}, err
	}
	return s, nil
}
func (m *Manager) Rename(id, name string) error {
	name, err := validName(name)
	if err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for i, s := range m.registry.Items {
		if s.ID == id {
			m.registry.Items[i].Name = name
			if err = m.persist(); err != nil {
				m.registry.Items[i] = s
			}
			return err
		}
	}
	return errors.New("空间不存在")
}
func (m *Manager) Archive(id string, archived bool) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if id == m.registry.ActiveID || id == m.registry.PendingID || id == "default" {
		return errors.New("当前空间、待切换空间与默认空间不能归档")
	}
	for i, s := range m.registry.Items {
		if s.ID == id {
			m.registry.Items[i].Archived = archived
			if err := m.persist(); err != nil {
				m.registry.Items[i] = s
				return err
			}
			return nil
		}
	}
	return errors.New("空间不存在")
}
