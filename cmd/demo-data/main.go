package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

type demoFile struct {
	Profile      store.Profile          `json:"profile"`
	Materials    []store.MaterialInput  `json:"materials"`
	Applications []demoApplication      `json:"applications"`
	Targets      []store.JobTargetInput `json:"targets"`
	Tasks        []demoTask             `json:"tasks"`
	Interviews   []demoInterview        `json:"interviews"`
	Offers       []demoOffer            `json:"offers"`
}
type demoApplication struct {
	store.CreateApplicationInput
}
type demoTask struct {
	Title, DueDate, Notes string
	Priority              int
}
type demoInterview struct {
	ApplicationCompany                                                     string `json:"applicationCompany"`
	Round, InterviewTime, Summary, Result, Questions, WeakPoints, FollowUp string
}
type demoOffer struct {
	ApplicationCompany string `json:"applicationCompany"`
	store.UpsertOfferInput
}

func main() {
	var input, output string
	flag.StringVar(&input, "input", "data.example/sample-data.json", "public JSON sample")
	flag.StringVar(&output, "output", "", "demo SQLite database")
	flag.Parse()
	if output == "" {
		fail(fmt.Errorf("-output is required"))
	}
	raw, err := os.ReadFile(input)
	if err != nil {
		fail(err)
	}
	var demo demoFile
	if err := json.Unmarshal(raw, &demo); err != nil {
		fail(err)
	}
	if len(demo.Applications) < 4 || len(demo.Materials) < 1 {
		fail(fmt.Errorf("sample data is too small"))
	}
	if err := os.MkdirAll(filepath.Dir(output), 0o755); err != nil {
		fail(err)
	}
	if _, err := os.Stat(output); err == nil {
		fail(fmt.Errorf("output already exists: %s", output))
	}
	st, err := store.Open(output)
	if err != nil {
		fail(err)
	}
	ctx := context.Background()
	ok := false
	defer func() {
		st.Close()
		if !ok {
			_ = os.Remove(output)
		}
	}()
	if err := st.SaveProfile(ctx, demo.Profile); err != nil {
		fail(err)
	}
	profile, err := st.GetProfile(ctx)
	if err != nil {
		fail(err)
	}
	mark(st, ctx, "profile", profile.ID)
	for _, item := range demo.Materials {
		id, err := st.CreateMaterial(ctx, item)
		if err != nil {
			fail(err)
		}
		mark(st, ctx, "material", id)
	}
	apps := map[string]int64{}
	for _, item := range demo.Applications {
		id, err := st.CreateApplication(ctx, item.CreateApplicationInput)
		if err != nil {
			fail(err)
		}
		application, err := st.GetApplication(ctx, id)
		if err != nil {
			fail(err)
		}
		mark(st, ctx, "application", id)
		mark(st, ctx, "resume", application.ResumeID)
		apps[application.CompanyName] = id
	}
	for _, item := range demo.Targets {
		id, err := st.CreateJobTarget(ctx, item)
		if err != nil {
			fail(err)
		}
		mark(st, ctx, "target", id)
	}
	for _, item := range demo.Tasks {
		id, err := st.CreateTask(ctx, store.CreateTaskInput{Title: item.Title, DueDate: item.DueDate, Priority: item.Priority, Notes: item.Notes})
		if err != nil {
			fail(err)
		}
		mark(st, ctx, "task", id)
	}
	for _, item := range demo.Interviews {
		applicationID := apps[item.ApplicationCompany]
		if applicationID == 0 {
			fail(fmt.Errorf("interview references unknown company: %s", item.ApplicationCompany))
		}
		id, err := st.CreateInterview(ctx, store.CreateInterviewInput{ApplicationID: applicationID, Round: item.Round, InterviewTime: item.InterviewTime, Summary: item.Summary, Result: item.Result, Questions: item.Questions, WeakPoints: item.WeakPoints, FollowUp: item.FollowUp})
		if err != nil {
			fail(err)
		}
		mark(st, ctx, "interview", id)
	}
	for _, item := range demo.Offers {
		applicationID := apps[item.ApplicationCompany]
		if applicationID == 0 {
			fail(fmt.Errorf("offer references unknown company: %s", item.ApplicationCompany))
		}
		item.ApplicationID = applicationID
		id, err := st.UpsertOffer(ctx, item.UpsertOfferInput)
		if err != nil {
			fail(err)
		}
		mark(st, ctx, "offer", id)
	}
	if err := st.Close(); err != nil {
		fail(err)
	}
	_ = os.Remove(output + "-wal")
	_ = os.Remove(output + "-shm")
	ok = true
	fmt.Printf("Demo database created: %s\n", output)
}

func mark(st *store.Store, ctx context.Context, kind string, id int64) {
	if err := st.MarkDemo(ctx, kind, id); err != nil {
		fail(err)
	}
}
func fail(err error) { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
