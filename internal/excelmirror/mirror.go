// Package excelmirror maintains the read-only Excel mirror beside the database.
// SQLite remains the source of truth; the workbook is rebuilt atomically.
package excelmirror

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/store"
	"github.com/xuri/excelize/v2"
)

const sheetName = "岗位投递"

var mirrorMu sync.Mutex

type column struct {
	title string
	width float64
}

var columns = []column{
	{"记录ID", 10}, {"公司", 20}, {"岗位", 25}, {"城市", 14},
	{"当前环节", 16}, {"当前情况", 20}, {"岗位类型", 16}, {"自定义标签", 24},
	{"优先级", 10}, {"状态更新时间", 20}, {"投递日期", 15}, {"网申截止", 18},
	{"下一步行动", 36}, {"下一步时间", 20}, {"最后跟进", 18}, {"面试反馈摘要", 44},
	{"简历路径", 36}, {"投递来源", 18}, {"岗位原始链接", 42}, {"JD 原文快照", 70},
}

// Sync rebuilds the workbook from current database records. It intentionally
// creates only the table-owned filter; a second worksheet auto-filter makes
// some Excel versions repair and remove the table on open.
func Sync(ctx context.Context, st *store.Store, destination string) error {
	mirrorMu.Lock()
	defer mirrorMu.Unlock()

	applications, err := st.ListApplications(ctx)
	if err != nil {
		return fmt.Errorf("读取投递记录: %w", err)
	}
	interviews, err := st.ListInterviews(ctx)
	if err != nil {
		return fmt.Errorf("读取面试记录: %w", err)
	}
	latestInterview := make(map[int64]string)
	for _, interview := range interviews {
		if _, exists := latestInterview[interview.ApplicationID]; exists {
			continue
		}
		parts := []string{strings.TrimSpace(interview.Round), strings.TrimSpace(interview.Result)}
		summary := strings.Join(nonEmpty(parts), " · ")
		if detail := strings.TrimSpace(interview.Summary); detail != "" {
			if summary != "" {
				summary += "\n"
			}
			summary += detail
		}
		latestInterview[interview.ApplicationID] = summary
	}

	if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
		return fmt.Errorf("准备 Excel 目录: %w", err)
	}
	temp := fmt.Sprintf("%s.%d.tmp.xlsx", destination, time.Now().UnixNano())
	defer os.Remove(temp)
	if err := writeWorkbook(temp, applications, latestInterview); err != nil {
		return err
	}
	if err := os.Rename(temp, destination); err != nil {
		return fmt.Errorf("替换 Excel 镜像（请先关闭已打开的工作簿）: %w", err)
	}
	_ = os.Chmod(destination, 0o600)
	return nil
}

func writeWorkbook(path string, applications []store.Application, interviews map[int64]string) error {
	f := excelize.NewFile()
	defer f.Close()
	if err := f.SetSheetName("Sheet1", sheetName); err != nil {
		return fmt.Errorf("命名工作表: %w", err)
	}
	if err := f.SetDocProps(&excelize.DocProperties{
		Creator:     "ResumeDetective",
		Title:       "秋招投递追踪",
		Subject:     "投递记录本地镜像",
		Description: "由 ResumeDetective 从本地数据库自动生成；请在软件中修改记录。",
	}); err != nil {
		return fmt.Errorf("设置工作簿属性: %w", err)
	}

	headerStyle, err := f.NewStyle(&excelize.Style{
		Font:      &excelize.Font{Bold: true, Color: "FFFFFF", Family: "微软雅黑", Size: 11},
		Fill:      excelize.Fill{Type: "pattern", Color: []string{"1F4E78"}, Pattern: 1},
		Alignment: &excelize.Alignment{Horizontal: "center", Vertical: "center"},
	})
	if err != nil {
		return fmt.Errorf("创建表头样式: %w", err)
	}
	bodyStyle, err := f.NewStyle(&excelize.Style{
		Font:      &excelize.Font{Family: "微软雅黑", Size: 10},
		Alignment: &excelize.Alignment{Vertical: "top", WrapText: true},
	})
	if err != nil {
		return fmt.Errorf("创建正文样式: %w", err)
	}
	linkStyle, err := f.NewStyle(&excelize.Style{
		Font:      &excelize.Font{Family: "微软雅黑", Size: 10, Color: "0969DA", Underline: "single"},
		Alignment: &excelize.Alignment{Vertical: "top", WrapText: true},
	})
	if err != nil {
		return fmt.Errorf("创建链接样式: %w", err)
	}

	for index, item := range columns {
		name, _ := excelize.ColumnNumberToName(index + 1)
		if err := f.SetCellValue(sheetName, name+"1", item.title); err != nil {
			return fmt.Errorf("写入表头: %w", err)
		}
		if err := f.SetColWidth(sheetName, name, name, item.width); err != nil {
			return fmt.Errorf("设置列宽: %w", err)
		}
	}
	if err := f.SetCellStyle(sheetName, "A1", "T1", headerStyle); err != nil {
		return fmt.Errorf("设置表头样式: %w", err)
	}
	_ = f.SetRowHeight(sheetName, 1, 26)

	for index, application := range applications {
		row := index + 2
		values := []any{
			application.ID, application.CompanyName, application.PositionName, optionalString(application.City),
			application.CurrentStatus, application.StageState, optionalString(application.Category), optionalString(application.Tags),
			application.Priority, optionalString(localTimestamp(application.StatusUpdateTime)), optionalString(application.AppliedAt),
			optionalString(application.ApplicationDeadline), optionalString(application.NextAction), optionalString(application.NextActionDueAt),
			optionalString(application.LastFollowUpAt), optionalString(interviews[application.ID]), optionalString(application.ResumePath),
			optionalString(application.Source), optionalString(application.JobLink), optionalString(application.JDText),
		}
		cell, _ := excelize.CoordinatesToCellName(1, row)
		if err := f.SetSheetRow(sheetName, cell, &values); err != nil {
			return fmt.Errorf("写入第 %d 行: %w", row, err)
		}
		if err := f.SetCellStyle(sheetName, fmt.Sprintf("A%d", row), fmt.Sprintf("T%d", row), bodyStyle); err != nil {
			return fmt.Errorf("设置第 %d 行样式: %w", row, err)
		}
		_ = f.SetRowHeight(sheetName, row, 48)
		if link := strings.TrimSpace(application.JobLink); link != "" {
			cell := fmt.Sprintf("S%d", row)
			if err := f.SetCellHyperLink(sheetName, cell, link, "External"); err != nil {
				return fmt.Errorf("设置岗位链接: %w", err)
			}
			if err := f.SetCellStyle(sheetName, cell, cell, linkStyle); err != nil {
				return fmt.Errorf("设置链接样式: %w", err)
			}
		}
	}

	lastRow := len(applications) + 1
	if len(applications) > 0 {
		striped := true
		if err := f.AddTable(sheetName, &excelize.Table{
			Range:          fmt.Sprintf("A1:T%d", lastRow),
			Name:           "Applications",
			StyleName:      "TableStyleMedium2",
			ShowRowStripes: &striped,
		}); err != nil {
			return fmt.Errorf("创建投递表: %w", err)
		}
		good, err := f.NewConditionalStyle(&excelize.Style{
			Font: &excelize.Font{Color: "09600B"}, Fill: excelize.Fill{Type: "pattern", Color: []string{"C7EECF"}, Pattern: 1},
		})
		if err != nil {
			return fmt.Errorf("创建 Offer 样式: %w", err)
		}
		bad, err := f.NewConditionalStyle(&excelize.Style{
			Font: &excelize.Font{Color: "9A0511"}, Fill: excelize.Fill{Type: "pattern", Color: []string{"FEC7CE"}, Pattern: 1},
		})
		if err != nil {
			return fmt.Errorf("创建终止样式: %w", err)
		}
		if err := f.SetConditionalFormat(sheetName, fmt.Sprintf("E2:E%d", lastRow), []excelize.ConditionalFormatOptions{
			{Type: "formula", Criteria: `E2="Offer"`, Format: &good},
			{Type: "formula", Criteria: `E2="终止"`, Format: &bad},
		}); err != nil {
			return fmt.Errorf("设置状态高亮: %w", err)
		}
	}

	showGridLines := false
	zoom := 90.0
	if err := f.SetSheetView(sheetName, 0, &excelize.ViewOptions{ShowGridLines: &showGridLines, ZoomScale: &zoom}); err != nil {
		return fmt.Errorf("设置工作表视图: %w", err)
	}
	if err := f.SetPanes(sheetName, &excelize.Panes{
		Freeze: true, YSplit: 1, TopLeftCell: "A2", ActivePane: "bottomLeft",
		Selection: []excelize.Selection{{SQRef: "A2", ActiveCell: "A2", Pane: "bottomLeft"}},
	}); err != nil {
		return fmt.Errorf("冻结表头: %w", err)
	}
	if err := f.SetColVisible(sheetName, "T", false); err != nil {
		return fmt.Errorf("隐藏 JD 快照列: %w", err)
	}
	if err := f.SaveAs(path); err != nil {
		return fmt.Errorf("保存 Excel 镜像: %w", err)
	}
	return nil
}

func localTimestamp(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return value
	}
	return parsed.Local().Format("2006-01-02 15:04:05")
}

func nonEmpty(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func optionalString(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}
