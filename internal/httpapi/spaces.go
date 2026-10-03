package httpapi

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/spaces"
)

// The boot session prevents stale tabs from writing or displaying another
// space's record with the same numeric ID, even after switching back.
func (s *Server) spaceBoundary(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/") && !strings.HasPrefix(r.URL.Path, "/resume/") {
			next.ServeHTTP(w, r)
			return
		}
		w.Header().Set("X-ResumeDetective-Session", s.session)
		// Do not make single-instance detection wait behind a long backup/import.
		if r.URL.Path == "/api/health" {
			next.ServeHTTP(w, r)
			return
		}
		exclusive := r.Method == "POST" && (r.URL.Path == "/api/backups" || r.URL.Path == "/api/updates/install" || strings.HasPrefix(r.URL.Path, "/api/spaces"))
		if exclusive {
			// Full snapshots and imports can legitimately take longer than ordinary API calls.
			_ = http.NewResponseController(w).SetWriteDeadline(time.Now().Add(5 * time.Minute))
			s.gate.Lock()
			defer s.gate.Unlock()
		} else {
			s.gate.RLock()
			defer s.gate.RUnlock()
		}
		w.Header().Set("X-ResumeDetective-Session", s.session)
		if s.spaces != nil && r.URL.Path != "/api/health" {
			token := r.Header.Get("X-ResumeDetective-Session")
			if strings.HasPrefix(r.URL.Path, "/resume/") || strings.HasPrefix(r.URL.Path, "/api/spaces/backups/") {
				token = r.URL.Query().Get("session")
			}
			if token != s.session {
				writeError(w, http.StatusConflict, "空间或服务已切换，请刷新页面后重试；旧页面未写入任何数据")
				return
			}
			if s.switching {
				writeError(w, http.StatusServiceUnavailable, "空间正在切换，请等待服务恢复后刷新")
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) selectSpaceDirectory(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	if s.pickDirectory == nil {
		writeError(w, http.StatusServiceUnavailable, "当前环境无法打开目录选择器，请粘贴目录路径")
		return
	}
	dir, err := s.pickDirectory(r.Context())
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"sourceDir": dir})
}
func (s *Server) activeSpace() spaces.Space {
	if s.spaces != nil {
		for _, space := range s.spaces.Snapshot().Items {
			if space.ID == s.spaceID {
				return space
			}
		}
	}
	return spaces.Space{ID: "default", Name: "默认空间"}
}
func (s *Server) requireSpaces(w http.ResponseWriter) bool {
	if s.spaces == nil {
		writeError(w, http.StatusServiceUnavailable, "当前程序未启用空间管理")
		return false
	}
	return true
}
func (s *Server) listSpaces(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"registry": s.spaces.Snapshot(), "current": s.activeSpace(), "recovery": s.spaces.Recovery(), "backup": spaces.Status(s.paths)})
}
func (s *Server) createSpace(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	var in struct {
		Name string `json:"name"`
	}
	if decodeJSON(w, r, &in) != nil {
		return
	}
	space, err := s.spaces.Create(in.Name)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, space)
}
func (s *Server) editSpace(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	var in struct {
		Name     *string `json:"name"`
		Archived *bool   `json:"archived"`
	}
	if decodeJSON(w, r, &in) != nil {
		return
	}
	var err error
	if in.Name != nil && in.Archived != nil {
		writeError(w, http.StatusBadRequest, "请分别提交重命名或归档操作")
		return
	}
	if in.Name != nil {
		err = s.spaces.Rename(r.PathValue("id"), *in.Name)
	} else if in.Archived != nil {
		err = s.spaces.Archive(r.PathValue("id"), *in.Archived)
	} else {
		writeError(w, http.StatusBadRequest, "缺少操作内容")
		return
	}
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
func (s *Server) switchSpace(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	if s.restart == nil {
		writeError(w, http.StatusServiceUnavailable, "当前环境不能重启切换")
		return
	}
	var in struct {
		ID string `json:"id"`
	}
	if decodeJSON(w, r, &in) != nil {
		return
	}
	if in.ID == s.spaceID {
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "restarting": false})
		return
	}
	if _, err := s.spaces.Paths(in.ID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	backup, err := spaces.Backup(r.Context(), s.store, s.paths, s.activeSpace(), "before-switch-")
	if err != nil {
		writeError(w, http.StatusBadRequest, "切换前完整备份失败，已留在原空间："+err.Error())
		return
	}
	if err = s.spaces.PrepareSwitch(in.ID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.switching = true
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "restarting": true, "backup": backup, "targetId": in.ID})
	go func() { time.Sleep(250 * time.Millisecond); s.restart() }()
}
func (s *Server) importSpace(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	var in struct {
		Name       string `json:"name"`
		Source     string `json:"source"`
		BackupName string `json:"backupName"`
	}
	if decodeJSON(w, r, &in) != nil {
		return
	}
	if in.Source != "" && in.BackupName != "" {
		writeError(w, http.StatusBadRequest, "请选择一种导入来源")
		return
	}
	source := strings.TrimSpace(in.Source)
	if in.BackupName != "" {
		if filepath.Base(in.BackupName) != in.BackupName || !strings.HasSuffix(in.BackupName, ".space.zip") {
			writeError(w, http.StatusBadRequest, "备份名称无效")
			return
		}
		source = filepath.Join(s.paths.BackupsDir, in.BackupName)
	}
	if source == "" {
		writeError(w, http.StatusBadRequest, "请填写 v4 数据目录或完整空间备份路径")
		return
	}
	space, err := s.spaces.Install(in.Name, func(p config.Paths) error {
		info, err := os.Lstat(source)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return os.ErrInvalid
		}
		if info.IsDir() {
			return spaces.ImportDirectory(r.Context(), source, p)
		}
		return spaces.Restore(r.Context(), source, p)
	})
	if err != nil {
		writeError(w, http.StatusBadRequest, "导入未完成，原空间未改动："+err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, space)
}
func (s *Server) listSpaceBackups(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	entries, err := os.ReadDir(s.paths.BackupsDir)
	if os.IsNotExist(err) {
		writeJSON(w, http.StatusOK, []any{})
		return
	}
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	items := []map[string]any{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".space.zip") {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		items = append(items, map[string]any{"name": e.Name(), "size": info.Size(), "createdAt": info.ModTime().Format(time.RFC3339)})
	}
	writeJSON(w, http.StatusOK, items)
}
func (s *Server) downloadSpaceBackup(w http.ResponseWriter, r *http.Request) {
	if !s.requireSpaces(w) {
		return
	}
	name := r.PathValue("name")
	if filepath.Base(name) != name || !strings.HasSuffix(name, ".space.zip") {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Disposition", `attachment; filename="`+name+`"`)
	http.ServeFile(w, r, filepath.Join(s.paths.BackupsDir, name))
}
