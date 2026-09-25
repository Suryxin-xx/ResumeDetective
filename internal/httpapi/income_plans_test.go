package httpapi

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestIncomePlanAPI(t *testing.T) {
	h := testHandler(t)
	call := func(method, path, body string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, "http://127.0.0.1"+path, bytes.NewBufferString(body))
		req.Host = "127.0.0.1:8765"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec
	}
	create := call(http.MethodPut, "/api/income-plans", `{"name":"测试薪资方案","parameters":{"version":1,"salary":{"monthlySalary":15000,"salaryMonths":13},"tax":{"year":2026},"hours":8,"days":5,"method":"combined"}}`)
	if create.Code != 200 {
		t.Fatalf("create: %d %s", create.Code, create.Body.String())
	}
	list := call(http.MethodGet, "/api/income-plans", "")
	if list.Code != 200 || !bytes.Contains(list.Body.Bytes(), []byte("测试薪资方案")) {
		t.Fatal(list.Body.String())
	}
	bad := call(http.MethodPut, "/api/income-plans", `{"name":"bad","parameters":{"version":2}}`)
	if bad.Code != 400 {
		t.Fatal("invalid accepted")
	}
	del := call(http.MethodDelete, "/api/income-plans/1", "")
	if del.Code != 200 {
		t.Fatal(del.Body.String())
	}
	list = call(http.MethodGet, "/api/income-plans", "")
	if bytes.Contains(list.Body.Bytes(), []byte("测试薪资方案")) {
		t.Fatal("delete failed")
	}
}
