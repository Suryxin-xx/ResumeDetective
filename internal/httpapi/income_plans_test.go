package httpapi

import (
	"bytes"
	"encoding/json"
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

func TestOfferIncomeUpdateAPI(t *testing.T) {
	h := testHandler(t)
	call := func(method, path, body string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, "http://127.0.0.1"+path, bytes.NewBufferString(body))
		req.Host = "127.0.0.1:8765"
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec
	}
	if rec := call(http.MethodPost, "/api/applications", `{"companyName":"示例公司","positionName":"研发"}`); rec.Code != 201 {
		t.Fatal(rec.Body.String())
	}
	if rec := call(http.MethodPut, "/api/offers", `{"applicationId":1,"monthlySalary":15000,"salaryMonths":13,"workIntensity":3,"growthScore":3,"interestScore":3,"locationScore":3,"stabilityScore":3,"notes":"保留备注"}`); rec.Code != 200 {
		t.Fatal(rec.Body.String())
	}
	var offers []struct { ID int64 `json:"id"`; UpdatedAt string `json:"updatedAt"` }
	beforeDuplicate := call(http.MethodGet, "/api/offers", "").Body.String()
	duplicate := call(http.MethodPut, "/api/offers", `{"createOnly":true,"applicationId":1,"monthlySalary":99999,"salaryMonths":13,"workIntensity":3,"growthScore":3,"interestScore":3,"locationScore":3,"stabilityScore":3,"notes":"不能覆盖"}`)
	if duplicate.Code != 400 || call(http.MethodGet, "/api/offers", "").Body.String() != beforeDuplicate {
		t.Fatal("duplicate create changed an existing offer")
	}
	json.Unmarshal(call(http.MethodGet, "/api/offers", "").Body.Bytes(), &offers)
	params := json.RawMessage(`{"version":1,"salary":{"monthlySalary":16000,"salaryMonths":13},"tax":{"enabled":true,"year":2026,"socialRate":10.5,"fundRate":8},"socialBaseMode":"salary","fundBaseMode":"salary","employerFundRate":12,"hours":8,"days":5,"method":"combined"}`)
	body, _ := json.Marshal(map[string]any{"parameters":params,"expectedUpdatedAt":offers[0].UpdatedAt})
	if rec := call(http.MethodPatch, "/api/offers/1/income", string(body)); rec.Code != 200 {
		t.Fatal(rec.Body.String())
	}
	if rec := call(http.MethodPatch, "/api/offers/1/income", string(body)); rec.Code != 400 {
		t.Fatal("stale API update accepted")
	}
	list := call(http.MethodGet, "/api/offers", "")
	if !bytes.Contains(list.Body.Bytes(), []byte("保留备注")) || !bytes.Contains(list.Body.Bytes(), []byte("incomeSettings")) {
		t.Fatal(list.Body.String())
	}
}
