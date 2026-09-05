package excelmirror

import (
	"archive/zip"
	"context"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Suryxin-xx/ResumeDetective/internal/store"
	"github.com/xuri/excelize/v2"
)

func TestSyncCreatesCompatibleTableWithoutDuplicateSheetFilter(t *testing.T) {
	dir := t.TempDir()
	st, err := store.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	if _, err := st.CreateApplication(ctx, store.CreateApplicationInput{
		CompanyName: "示例公司", PositionName: "产品经理", JobLink: "https://example.com/job", CurrentStatus: "测评",
		Category: "产品", Tags: "校招,重点", StageState: "已安排", StageTimeType: "deadline",
		StageScheduledAt: "2026-09-10T23:59", StageTimeNote: "链接失效前完成",
	}); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "秋招投递追踪.xlsx")
	if err := Sync(ctx, st, path); err != nil {
		t.Fatal(err)
	}

	f, err := excelize.OpenFile(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	tables, err := f.GetTables(sheetName)
	if err != nil {
		t.Fatal(err)
	}
	if len(tables) != 1 || tables[0].Name != "Applications" || tables[0].Range != "A1:X2" {
		t.Fatalf("unexpected tables: %+v", tables)
	}
	if value, err := f.GetCellValue(sheetName, "B2"); err != nil || value != "示例公司" {
		t.Fatalf("B2=%q err=%v", value, err)
	}
	for cell, want := range map[string]string{"G2": "产品", "H2": "校招,重点", "I2": "截止时间", "J2": "2026-09-10 23:59:00", "L2": "链接失效前完成"} {
		if value, err := f.GetCellValue(sheetName, cell); err != nil || value != want {
			t.Fatalf("%s=%q err=%v, want %q", cell, value, err, want)
		}
	}
	dimension, err := f.GetSheetDimension(sheetName)
	if err != nil {
		t.Fatal(err)
	}
	if dimension != "A1:X2" {
		t.Fatalf("worksheet dimension=%q, want A1:X2", dimension)
	}

	archive, err := zip.OpenReader(path)
	if err != nil {
		t.Fatal(err)
	}
	defer archive.Close()
	sheetXML := readZipEntry(t, archive.File, "xl/worksheets/sheet1.xml")
	tableXML := readZipEntry(t, archive.File, "xl/tables/table1.xml")
	if strings.Contains(sheetXML, "<autoFilter") {
		t.Fatal("worksheet contains a second autoFilter outside the structured table")
	}
	if !strings.Contains(tableXML, "<autoFilter") {
		t.Fatal("structured table is missing its autoFilter")
	}
	if !strings.Contains(sheetXML, `<dimension ref="A1:X2"`) {
		t.Fatal("worksheet dimension does not match the structured table range")
	}
}

func readZipEntry(t *testing.T, files []*zip.File, name string) string {
	t.Helper()
	for _, file := range files {
		if file.Name != name {
			continue
		}
		reader, err := file.Open()
		if err != nil {
			t.Fatal(err)
		}
		defer reader.Close()
		data, err := io.ReadAll(reader)
		if err != nil {
			t.Fatal(err)
		}
		return string(data)
	}
	if _, err := os.Stat(name); err == nil {
		t.Fatalf("unexpected filesystem entry %s", name)
	}
	t.Fatalf("zip entry %s not found", name)
	return ""
}
