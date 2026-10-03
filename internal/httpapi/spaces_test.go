package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync"
	"testing"
	"testing/fstest"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/spaces"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

func spaceRequest(h http.Handler, method, path, body, session string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, "http://127.0.0.1:8765"+path, bytes.NewBufferString(body))
	req.Header.Set("X-ResumeDetective-Session", session)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestHealthDoesNotWaitForContentGate(t *testing.T) {
	gate := &sync.RWMutex{}
	s := &Server{gate: gate, session: "boot"}
	h := s.spaceBoundary(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	gate.Lock()
	defer gate.Unlock()
	done := make(chan int, 1)
	go func() { done <- spaceRequest(h, "GET", "/api/health", "", "").Code }()
	select {
	case code := <-done:
		if code != 200 {
			t.Fatal(code)
		}
	case <-time.After(time.Second):
		t.Fatal("health blocked behind backup")
	}
}
func TestSpaceSessionRejectsStaleWritesAndCrossSpaceIDs(t *testing.T) {
	p, err := config.Resolve(filepath.Join(t.TempDir(), "data"))
	if err != nil {
		t.Fatal(err)
	}
	m, err := spaces.Open(p, "秋招")
	if err != nil {
		t.Fatal(err)
	}
	original, _, _, err := m.OpenSelected()
	if err != nil {
		t.Fatal(err)
	}
	defer original.Close()
	m.Commit("default")
	ctx := context.Background()
	original.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: "秋招", PositionName: "原岗位"})
	newSpace, err := m.Create("春招")
	if err != nil {
		t.Fatal(err)
	}
	target, _ := m.Paths(newSpace.ID)
	spring, err := store.Open(target.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer spring.Close()
	spring.CreateApplication(ctx, store.CreateApplicationInput{CompanyName: "春招", PositionName: "新岗位"})
	web := fstest.MapFS{"index.html": {Data: []byte("ui")}}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	newHandler := func(st *store.Store, paths config.Paths, id, session string) http.Handler {
		return NewWithOptions(st, web, paths, "", nil, logger, Options{Spaces: m, SpaceID: id, Session: session, Gate: &sync.RWMutex{}, Restart: func() {}})
	}
	h := newHandler(spring, target, newSpace.ID, "new-boot")
	for _, token := range []string{"", "old-boot"} {
		for _, call := range [][3]string{{"GET", "/api/applications", ""}, {"PATCH", "/api/applications/1", `{"companyName":"覆盖","positionName":"错岗位"}`}, {"DELETE", "/api/applications/1", ""}} {
			rec := spaceRequest(h, call[0], call[1], call[2], token)
			if rec.Code != http.StatusConflict {
				t.Fatalf("stale request %v: %d %s", call, rec.Code, rec.Body.String())
			}
		}
	}
	items, _ := spring.ListApplications(ctx)
	if len(items) != 1 || items[0].CompanyName != "春招" {
		t.Fatal("stale page changed new space")
	}
	health := spaceRequest(h, "GET", "/api/health", "", "")
	if health.Code != 200 || !bytes.Contains(health.Body.Bytes(), []byte("new-boot")) {
		t.Fatal("health handshake failed")
	}
	good := spaceRequest(h, "GET", "/api/applications", "", "new-boot")
	if good.Code != 200 {
		t.Fatal(good.Body.String())
	}
	resume := spaceRequest(h, "GET", "/resume/1?session=old-boot", "", "")
	if resume.Code != 409 {
		t.Fatal("old resume link not blocked")
	}
	defaultHandler := newHandler(original, p, "default", "default-boot")
	created := spaceRequest(defaultHandler, "POST", "/api/spaces", `{"name":"额外空间"}`, "default-boot")
	if created.Code != 201 {
		t.Fatal(created.Body.String())
	}
	switchBody, _ := json.Marshal(map[string]string{"id": newSpace.ID})
	switched := spaceRequest(defaultHandler, "POST", "/api/spaces/switch", string(switchBody), "default-boot")
	if switched.Code != 202 {
		t.Fatalf("switch: %d %s", switched.Code, switched.Body.String())
	}
	blocked := spaceRequest(defaultHandler, "POST", "/api/applications", `{"companyName":"停止","positionName":"写入"}`, "default-boot")
	if blocked.Code != 503 {
		t.Fatal("writes were allowed during switch")
	}
	if m.Snapshot().ActiveID != "default" || m.Snapshot().PendingID != newSpace.ID {
		t.Fatal("switch activation was not transactional")
	}
	list := spaceRequest(h, "GET", "/api/spaces/backups", "", "new-boot")
	if list.Code != 200 {
		t.Fatal(list.Body.String())
	}
}

func TestSpaceImportFailureKeepsOriginalRecords(t *testing.T) {
	p, err := config.Resolve(filepath.Join(t.TempDir(), "data"))
	if err != nil {
		t.Fatal(err)
	}
	m, err := spaces.Open(p, "秋招")
	if err != nil {
		t.Fatal(err)
	}
	st, _, _, err := m.OpenSelected()
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	st.CreateApplication(context.Background(), store.CreateApplicationInput{CompanyName: "保留", PositionName: "真实岗位"})
	h := NewWithOptions(st, fstest.MapFS{"index.html": {Data: []byte("ui")}}, p, "", nil, slog.New(slog.NewTextHandler(io.Discard, nil)), Options{Spaces: m, SpaceID: "default", Session: "test"})
	rec := spaceRequest(h, "POST", "/api/spaces/import", `{"name":"失败副本","source":"Z:/does-not-exist"}`, "test")
	if rec.Code != 400 || len(m.Snapshot().Items) != 1 {
		t.Fatal("invalid import published")
	}
	items, _ := st.ListApplications(context.Background())
	if len(items) != 1 || items[0].CompanyName != "保留" {
		t.Fatal("failed import changed original")
	}
	rec = spaceRequest(h, "POST", "/api/backups", "{}", "test")
	if rec.Code != http.StatusCreated {
		t.Fatal(rec.Body.String())
	}
	if !bytes.Contains(rec.Body.Bytes(), []byte(".space.zip")) {
		t.Fatal("manual backup did not include full space")
	}
}
