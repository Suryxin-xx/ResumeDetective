package store

import (
	"context"
	"path/filepath"
	"strings"
	"testing"
)

func TestTaskAndInterviewWorkflow(t *testing.T) {
	ctx := context.Background()
	st, err := Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	appID, err := st.CreateApplication(ctx, CreateApplicationInput{CompanyName: "流程公司", PositionName: "后端"})
	if err != nil {
		t.Fatal(err)
	}
	taskID, err := st.CreateTask(ctx, CreateTaskInput{Title: "复习网络", DueDate: "2026-08-03", Priority: 3})
	if err != nil {
		t.Fatal(err)
	}
	if err := st.SetTaskState(ctx, taskID, "done"); err != nil {
		t.Fatal(err)
	}
	tasks, err := st.ListTasks(ctx)
	if err != nil || len(tasks) != 1 || tasks[0].State != "done" {
		t.Fatalf("tasks=%#v err=%v", tasks, err)
	}
	interviewID, err := st.CreateInterview(ctx, CreateInterviewInput{ApplicationID: appID, Round: "一面", InterviewTime: "2026-09-08T14:00", InterviewMode: "视频面试", MeetingLink: "https://meeting.example.com/room", ScheduleNotes: "提前 10 分钟入会", Result: "待面试", Questions: "网络分层", WeakPoints: "HTTP/3", FollowUp: "复习 QUIC"})
	if err != nil {
		t.Fatal(err)
	}
	interviews, err := st.ListInterviews(ctx)
	if err != nil || len(interviews) != 1 || interviews[0].CompanyName != "流程公司" || interviews[0].InterviewMode != "视频面试" || interviews[0].MeetingLink != "https://meeting.example.com/room" || interviews[0].ScheduleNotes != "提前 10 分钟入会" {
		t.Fatalf("interviews=%#v err=%v", interviews, err)
	}
	if _, err := st.CreateInterview(ctx, CreateInterviewInput{ApplicationID: appID, Round: "一面", MeetingLink: "javascript:alert(1)"}); err == nil {
		t.Fatal("expected invalid meeting link to be rejected")
	}
	if err := st.UpdateInterview(ctx, interviewID, CreateInterviewInput{ApplicationID: appID, Round: "二面", Result: "通过", Summary: "项目追问深入", Questions: "缓存一致性", WeakPoints: "消息队列", FollowUp: "复盘项目"}); err != nil {
		t.Fatal(err)
	}
	interviews, err = st.ListInterviews(ctx)
	if err != nil || len(interviews) != 1 || interviews[0].Round != "二面" || interviews[0].Result != "通过" || interviews[0].Summary != "项目追问深入" {
		t.Fatalf("updated interviews=%#v err=%v", interviews, err)
	}
	if err := st.DeleteInterview(ctx, interviewID); err != nil {
		t.Fatal(err)
	}
	if err := st.DeleteTask(ctx, taskID); err != nil {
		t.Fatal(err)
	}
}

func TestInterviewStageSyncKeepsCoarseApplicationStatus(t *testing.T) {
	ctx := context.Background()
	st, err := Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	appID, err := st.CreateApplication(ctx, CreateApplicationInput{CompanyName: "轮次公司", PositionName: "产品", CurrentStatus: "简历筛选", StageState: "待处理"})
	if err != nil {
		t.Fatal(err)
	}
	changed, err := st.SyncApplicationInterviewStage(ctx, appID, "二面", "待面试")
	if err != nil || !changed {
		t.Fatalf("first sync changed=%v err=%v", changed, err)
	}
	app, err := st.GetApplication(ctx, appID)
	if err != nil || app.CurrentStatus != "业务面试" || app.StageState != "已安排" || !strings.Contains(app.StatusHistory[len(app.StatusHistory)-1].Note, "二面") {
		t.Fatalf("application=%#v err=%v", app, err)
	}
	changed, err = st.SyncApplicationInterviewStage(ctx, appID, "二面", "待面试")
	if err != nil || changed {
		t.Fatalf("idempotent sync changed=%v err=%v", changed, err)
	}
	changed, err = st.SyncApplicationInterviewStage(ctx, appID, "HR 面", "待确认")
	if err != nil || !changed {
		t.Fatalf("HR sync changed=%v err=%v", changed, err)
	}
	app, err = st.GetApplication(ctx, appID)
	if err != nil || app.CurrentStatus != "HR 面" || app.StageState != "已完成，等待结果" {
		t.Fatalf("HR application=%#v err=%v", app, err)
	}
	if err := st.UpdateApplication(ctx, appID, UpdateApplicationInput{CurrentStatus: "Offer", StageState: "已完成", Priority: app.Priority, City: app.City, Source: app.Source, JobLink: app.JobLink, Category: app.Category, Tags: app.Tags, JDText: app.JDText, AppliedAt: app.AppliedAt}); err != nil {
		t.Fatal(err)
	}
	changed, err = st.SyncApplicationInterviewStage(ctx, appID, "三面", "未通过")
	if err != nil || changed {
		t.Fatalf("terminal sync changed=%v err=%v", changed, err)
	}
	app, _ = st.GetApplication(ctx, appID)
	if app.CurrentStatus != "Offer" {
		t.Fatalf("finished application was overwritten: %#v", app)
	}
}
