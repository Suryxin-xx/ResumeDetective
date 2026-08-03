package httpapi

import (
	"bytes"
	"context"
	"io/fs"
	"log/slog"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"testing/fstest"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

func testHandler(t *testing.T) http.Handler {
	t.Helper()
	st, err := store.Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { st.Close() })
	web := fstest.MapFS{"index.html": &fstest.MapFile{Data: []byte("ok"), Mode: fs.FileMode(0o644)}}
	dataDir := t.TempDir()
	paths, err := config.Resolve(dataDir)
	if err != nil {
		t.Fatal(err)
	}
	return New(st, web, paths, "", nil, slog.New(slog.NewTextHandler(os.Stderr, nil)))
}

func TestLocalHostAndApplicationAPI(t *testing.T) {
	h := testHandler(t)
	req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications", bytes.NewBufferString(`{"companyName":"示例","positionName":"后端"}`))
	req.Host = "127.0.0.1:8765"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create status %d: %s", rec.Code, rec.Body.String())
	}
	req = httptest.NewRequest(http.MethodGet, "http://127.0.0.1/api/applications", nil)
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || !bytes.Contains(rec.Body.Bytes(), []byte("示例")) {
		t.Fatalf("list: %d %s", rec.Code, rec.Body.String())
	}
}

func TestRejectsForeignHost(t *testing.T) {
	h := testHandler(t)
	req := httptest.NewRequest(http.MethodGet, "http://evil.example/api/health", nil)
	req.Host = "evil.example"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d", rec.Code)
	}
}

func TestRejectsCrossOriginMutation(t *testing.T) {
	h := testHandler(t)
	req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications", bytes.NewBufferString(`{"companyName":"示例","positionName":"后端"}`))
	req.Host = "127.0.0.1:8765"
	req.Header.Set("Origin", "https://evil.example")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d", rec.Code)
	}
}

func TestUploadAndServeResume(t *testing.T) {
	h := testHandler(t)
	req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications", bytes.NewBufferString(`{"companyName":"简历公司","positionName":"后端"}`))
	req.Host = "127.0.0.1:8765"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create: %d %s", rec.Code, rec.Body.String())
	}

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("resume", "resume.pdf")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = part.Write([]byte("%PDF-1.4\n%%EOF"))
	_ = writer.Close()
	req = httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications/1/resume", &body)
	req.Host = "127.0.0.1:8765"
	req.Header.Set("Content-Type", writer.FormDataContentType())
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload: %d %s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodGet, "http://127.0.0.1/resume/1", nil)
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || rec.Header().Values("Content-Length") == nil || len(rec.Header().Values("Content-Length")) != 1 {
		t.Fatalf("serve resume: %d headers=%v", rec.Code, rec.Header())
	}
}

func TestSelectInspectAndImportExplicitV3Directory(t *testing.T) {
	root := t.TempDir()
	sourceDir := filepath.Join(root, "Python v3 data")
	if err := os.MkdirAll(sourceDir, 0o700); err != nil {
		t.Fatal(err)
	}
	legacy, err := store.Open(filepath.Join(sourceDir, "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := legacy.CreateApplication(context.Background(), store.CreateApplicationInput{CompanyName: "迁移公司", PositionName: "后端"}); err != nil {
		t.Fatal(err)
	}
	if err := legacy.Close(); err != nil {
		t.Fatal(err)
	}

	paths, err := config.Resolve(filepath.Join(root, "v4"))
	if err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(paths.Database)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { st.Close() })
	web := fstest.MapFS{"index.html": &fstest.MapFile{Data: []byte("ok"), Mode: fs.FileMode(0o644)}}
	h := NewWithOptions(st, web, paths, "", nil, slog.New(slog.NewTextHandler(os.Stderr, nil)), Options{
		PickDirectory: func(context.Context) (string, error) { return sourceDir, nil },
	})

	req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/migration/select", bytes.NewBufferString(`{}`))
	req.Host = "127.0.0.1:8765"
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || !bytes.Contains(rec.Body.Bytes(), []byte(`"available":true`)) || !bytes.Contains(rec.Body.Bytes(), []byte(`"applications":1`)) {
		t.Fatalf("select: %d %s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/migration/inspect", bytes.NewBufferString(`{"sourceDir":"`+filepath.ToSlash(filepath.Join(sourceDir, "data.db"))+`"}`))
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || !bytes.Contains(rec.Body.Bytes(), []byte(`"available":true`)) {
		t.Fatalf("inspect: %d %s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/migration/import", bytes.NewBufferString(`{"sourceDir":"`+filepath.ToSlash(sourceDir)+`"}`))
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated || !bytes.Contains(rec.Body.Bytes(), []byte(`"imported":true`)) {
		t.Fatalf("import: %d %s", rec.Code, rec.Body.String())
	}

	apps, err := st.ListApplications(context.Background())
	if err != nil || len(apps) != 1 || apps[0].CompanyName != "迁移公司" {
		t.Fatalf("apps=%#v err=%v", apps, err)
	}
}
