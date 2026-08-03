package store

import (
	"context"
	"path/filepath"
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
	interviewID, err := st.CreateInterview(ctx, CreateInterviewInput{ApplicationID: appID, Round: "一面", Result: "待确认", Questions: "网络分层", WeakPoints: "HTTP/3", FollowUp: "复习 QUIC"})
	if err != nil {
		t.Fatal(err)
	}
	interviews, err := st.ListInterviews(ctx)
	if err != nil || len(interviews) != 1 || interviews[0].CompanyName != "流程公司" {
		t.Fatalf("interviews=%#v err=%v", interviews, err)
	}
	if err := st.DeleteInterview(ctx, interviewID); err != nil {
		t.Fatal(err)
	}
	if err := st.DeleteTask(ctx, taskID); err != nil {
		t.Fatal(err)
	}
}
