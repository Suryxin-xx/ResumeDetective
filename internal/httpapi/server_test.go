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

func TestInterviewCanBeEdited(t *testing.T) {
	h := testHandler(t)
	createApplication := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications", bytes.NewBufferString(`{"companyName":"示例","positionName":"后端"}`))
	createApplication.Host = "127.0.0.1:8765"
	applicationResponse := httptest.NewRecorder()
	h.ServeHTTP(applicationResponse, createApplication)
	if applicationResponse.Code != http.StatusCreated {
		t.Fatalf("create application: %d %s", applicationResponse.Code, applicationResponse.Body.String())
	}
	createInterview := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/interviews", bytes.NewBufferString(`{"applicationId":1,"round":"一面","result":"待确认"}`))
	createInterview.Host = "127.0.0.1:8765"
	interviewResponse := httptest.NewRecorder()
	h.ServeHTTP(interviewResponse, createInterview)
	if interviewResponse.Code != http.StatusCreated {
		t.Fatalf("create interview: %d %s", interviewResponse.Code, interviewResponse.Body.String())
	}
	updateInterview := httptest.NewRequest(http.MethodPatch, "http://127.0.0.1/api/interviews/1", bytes.NewBufferString(`{"applicationId":1,"round":"二面","result":"通过","summary":"项目追问深入"}`))
	updateInterview.Host = "127.0.0.1:8765"
	updateResponse := httptest.NewRecorder()
	h.ServeHTTP(updateResponse, updateInterview)
	if updateResponse.Code != http.StatusOK {
		t.Fatalf("update interview: %d %s", updateResponse.Code, updateResponse.Body.String())
	}
	listInterviews := httptest.NewRequest(http.MethodGet, "http://127.0.0.1/api/interviews", nil)
	listInterviews.Host = "127.0.0.1:8765"
	listResponse := httptest.NewRecorder()
	h.ServeHTTP(listResponse, listInterviews)
	if listResponse.Code != http.StatusOK || !bytes.Contains(listResponse.Body.Bytes(), []byte(`"round":"二面"`)) || !bytes.Contains(listResponse.Body.Bytes(), []byte(`"result":"通过"`)) {
		t.Fatalf("list interviews: %d %s", listResponse.Code, listResponse.Body.String())
	}
}

func TestPreUpdateBackupPreservesApplications(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "source.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { st.Close() })
	if _, err := st.CreateApplication(context.Background(), store.CreateApplicationInput{CompanyName: "更新备份公司", PositionName: "测试岗位"}); err != nil {
		t.Fatal(err)
	}
	server := &Server{store: st, backupsDir: filepath.Join(dir, "backups")}
	backupPath, err := server.createPreUpdateBackup(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	backupStore, err := store.Open(backupPath)
	if err != nil {
		t.Fatal(err)
	}
	defer backupStore.Close()
	items, err := backupStore.ListApplications(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].CompanyName != "更新备份公司" {
		t.Fatalf("unexpected backup content: %#v", items)
	}
}

func TestInterviewStageCanSyncApplication(t *testing.T) {
	h := testHandler(t)
	createApplication := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications", bytes.NewBufferString(`{"companyName":"示例","positionName":"后端","currentStatus":"简历筛选","stageState":"待处理"}`))
	createApplication.Host = "127.0.0.1:8765"
	applicationResponse := httptest.NewRecorder()
	h.ServeHTTP(applicationResponse, createApplication)
	if applicationResponse.Code != http.StatusCreated {
		t.Fatalf("create application: %d %s", applicationResponse.Code, applicationResponse.Body.String())
	}
	syncRequest := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications/1/interview-stage", bytes.NewBufferString(`{"round":"二面","result":"待面试"}`))
	syncRequest.Host = "127.0.0.1:8765"
	syncResponse := httptest.NewRecorder()
	h.ServeHTTP(syncResponse, syncRequest)
	if syncResponse.Code != http.StatusOK || !bytes.Contains(syncResponse.Body.Bytes(), []byte(`"changed":true`)) {
		t.Fatalf("sync stage: %d %s", syncResponse.Code, syncResponse.Body.String())
	}
	listRequest := httptest.NewRequest(http.MethodGet, "http://127.0.0.1/api/applications", nil)
	listRequest.Host = "127.0.0.1:8765"
	listResponse := httptest.NewRecorder()
	h.ServeHTTP(listResponse, listRequest)
	if listResponse.Code != http.StatusOK || !bytes.Contains(listResponse.Body.Bytes(), []byte(`"currentStatus":"业务面试"`)) || !bytes.Contains(listResponse.Body.Bytes(), []byte(`"stageState":"已安排"`)) || !bytes.Contains(listResponse.Body.Bytes(), []byte(`由二面记录同步`)) {
		t.Fatalf("list applications: %d %s", listResponse.Code, listResponse.Body.String())
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
	req = httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications/1/resume/rename", nil)
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || !bytes.Contains(rec.Body.Bytes(), []byte(`"fileName":"简历公司-后端.pdf"`)) {
		t.Fatalf("rename: %d %s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodGet, "http://127.0.0.1/resume/1", nil)
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || rec.Header().Values("Content-Length") == nil || len(rec.Header().Values("Content-Length")) != 1 {
		t.Fatalf("serve resume: %d headers=%v", rec.Code, rec.Header())
	}
}

func TestLinkExistingResumeAcrossApplications(t *testing.T) {
	h := testHandler(t)
	for _, payload := range []string{
		`{"companyName":"源公司","positionName":"产品"}`,
		`{"companyName":"目标公司","positionName":"运营"}`,
	} {
		req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications", bytes.NewBufferString(payload))
		req.Host = "127.0.0.1:8765"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			t.Fatalf("create application: %d %s", rec.Code, rec.Body.String())
		}
	}

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("resume", "shared.pdf")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = part.Write([]byte("%PDF-1.4\nshared\n%%EOF"))
	_ = writer.Close()
	req := httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications/1/resume", &body)
	req.Host = "127.0.0.1:8765"
	req.Header.Set("Content-Type", writer.FormDataContentType())
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("upload: %d %s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodPost, "http://127.0.0.1/api/applications/2/resume/link", bytes.NewBufferString(`{"sourceApplicationId":1}`))
	req.Host = "127.0.0.1:8765"
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || !bytes.Contains(rec.Body.Bytes(), []byte(`"fileName":"shared.pdf"`)) {
		t.Fatalf("link: %d %s", rec.Code, rec.Body.String())
	}

	for _, id := range []string{"1", "2"} {
		req = httptest.NewRequest(http.MethodGet, "http://127.0.0.1/resume/"+id, nil)
		req.Host = "127.0.0.1:8765"
		rec = httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK || !bytes.Contains(rec.Body.Bytes(), []byte("shared")) {
			t.Fatalf("serve linked resume %s: %d %s", id, rec.Code, rec.Body.String())
		}
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
