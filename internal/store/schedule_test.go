package store

import (
	"context"
	"path/filepath"
	"testing"
)

func TestApplicationStageSchedulePersistsAndCompletes(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "schedule.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	id, err := st.CreateApplication(ctx, CreateApplicationInput{
		CompanyName: "示例公司", PositionName: "测试岗位", CurrentStatus: "测评", StageState: "已安排",
		StageTimeType: "deadline", StageScheduledAt: "2026-09-10T23:59", StageTimeNote: "邮件链接到期",
	})
	if err != nil {
		t.Fatal(err)
	}
	item, err := st.GetApplication(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	if item.StageTimeType != "deadline" || item.StageScheduledAt != "2026-09-10T23:59" || item.StageTimeNote != "邮件链接到期" {
		t.Fatalf("unexpected schedule: %+v", item)
	}
	if err := st.UpdateApplication(ctx, id, UpdateApplicationInput{
		CurrentStatus: item.CurrentStatus, StageState: "已完成，等待结果", Priority: item.Priority,
		StageTimeType: item.StageTimeType, StageScheduledAt: item.StageScheduledAt, StageTimeNote: item.StageTimeNote,
	}); err != nil {
		t.Fatal(err)
	}
	item, err = st.GetApplication(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	if item.StageCompletedAt == "" {
		t.Fatal("moving an arranged stage to waiting should record the actual completion time")
	}
	if len(item.StatusHistory) < 2 || item.StatusHistory[len(item.StatusHistory)-1].Note == "" {
		t.Fatalf("schedule transition missing from history: %+v", item.StatusHistory)
	}
}

func TestApplicationScheduleRequiresKnownType(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "invalid.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if _, err := st.CreateApplication(context.Background(), CreateApplicationInput{
		CompanyName: "示例公司", PositionName: "测试岗位", StageScheduledAt: "2026-09-10",
	}); err == nil {
		t.Fatal("schedule without a type should fail")
	}
}

func TestChangingStageClearsUnchangedSchedule(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "stage-change.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	ctx := context.Background()
	id, err := st.CreateApplication(ctx, CreateApplicationInput{
		CompanyName: "示例公司", PositionName: "测试岗位", CurrentStatus: "测评", StageState: "已安排",
		StageTimeType: "deadline", StageScheduledAt: "2026-09-10T23:59", StageTimeNote: "测评截止",
	})
	if err != nil {
		t.Fatal(err)
	}
	item, err := st.GetApplication(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	if err := st.UpdateApplication(ctx, id, UpdateApplicationInput{
		CurrentStatus: "业务面试", StageState: "待处理", Priority: item.Priority,
		StageTimeType: item.StageTimeType, StageScheduledAt: item.StageScheduledAt,
		StageCompletedAt: item.StageCompletedAt, StageTimeNote: item.StageTimeNote,
	}); err != nil {
		t.Fatal(err)
	}
	item, err = st.GetApplication(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	if item.StageTimeType != "" || item.StageScheduledAt != "" || item.StageCompletedAt != "" || item.StageTimeNote != "" {
		t.Fatalf("old stage schedule leaked into new stage: %+v", item)
	}
}
