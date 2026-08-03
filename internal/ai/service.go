package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/settings"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

const maxResponseBytes = 4 << 20

type Service struct {
	store    *store.Store
	settings *settings.Manager
	workDir  string
	client   *http.Client
}

type Request struct {
	Kind          string `json:"kind"`
	ApplicationID int64  `json:"applicationId"`
	ExtraContext  string `json:"extraContext"`
}

type Result struct {
	Provider string `json:"provider"`
	Model    string `json:"model"`
	Content  any    `json:"content"`
	Raw      string `json:"raw,omitempty"`
	Duration int64  `json:"durationMs"`
}

type TestResult struct {
	OK       bool   `json:"ok"`
	Provider string `json:"provider"`
	Message  string `json:"message"`
}

type BalanceInfo struct {
	Currency        string `json:"currency"`
	TotalBalance    string `json:"totalBalance"`
	GrantedBalance  string `json:"grantedBalance"`
	ToppedUpBalance string `json:"toppedUpBalance"`
}

type BalanceResult struct {
	Available bool          `json:"available"`
	Balances  []BalanceInfo `json:"balances"`
	CheckedAt time.Time     `json:"checkedAt"`
}

func New(st *store.Store, manager *settings.Manager, workDir string) *Service {
	return &Service{store: st, settings: manager, workDir: workDir, client: &http.Client{Timeout: 90 * time.Second}}
}

func (s *Service) Test(ctx context.Context) (TestResult, error) {
	cfg := s.settings.Get().AI
	if cfg.Mode == "reasonix" {
		path, err := validateReasonix(cfg.ReasonixPath)
		if err != nil {
			return TestResult{}, err
		}
		cmd := exec.CommandContext(ctx, path, "--version")
		cmd.Dir = s.workDir
		output, err := cmd.CombinedOutput()
		if err != nil {
			return TestResult{}, fmt.Errorf("Reasonix 启动失败: %w", err)
		}
		return TestResult{OK: true, Provider: "reasonix", Message: strings.TrimSpace(string(output))}, nil
	}
	key := strings.TrimSpace(os.Getenv("DEEPSEEK_API_KEY"))
	if key == "" {
		return TestResult{}, errors.New("尚未配置 DeepSeek API Key")
	}
	endpoint, err := joinEndpoint(cfg.BaseURL, "models")
	if err != nil {
		return TestResult{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return TestResult{}, err
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "ResumeDetective/4")
	resp, err := s.client.Do(req)
	if err != nil {
		return TestResult{}, fmt.Errorf("连接 DeepSeek 失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return TestResult{}, apiStatusError(resp)
	}
	return TestResult{OK: true, Provider: "deepseek", Message: "连接成功，密钥有效"}, nil
}

// Balance queries DeepSeek only when the user explicitly requests it. The
// response is returned to the browser but is never persisted locally.
func (s *Service) Balance(ctx context.Context) (BalanceResult, error) {
	cfg := s.settings.Get().AI
	if cfg.Mode != "direct" {
		return BalanceResult{}, errors.New("余额查询仅适用于 DeepSeek API 直连模式")
	}
	key := strings.TrimSpace(os.Getenv("DEEPSEEK_API_KEY"))
	if key == "" {
		return BalanceResult{}, errors.New("尚未配置 DeepSeek API Key")
	}
	endpoint, err := joinEndpoint(cfg.BaseURL, "user/balance")
	if err != nil {
		return BalanceResult{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return BalanceResult{}, err
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "ResumeDetective/4")
	resp, err := s.client.Do(req)
	if err != nil {
		return BalanceResult{}, fmt.Errorf("查询 DeepSeek 余额失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return BalanceResult{}, apiStatusError(resp)
	}
	var decoded struct {
		Available bool `json:"is_available"`
		Balances  []struct {
			Currency        string `json:"currency"`
			TotalBalance    string `json:"total_balance"`
			GrantedBalance  string `json:"granted_balance"`
			ToppedUpBalance string `json:"topped_up_balance"`
		} `json:"balance_infos"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 256<<10)).Decode(&decoded); err != nil {
		return BalanceResult{}, errors.New("DeepSeek 余额返回内容无法解析")
	}
	result := BalanceResult{Available: decoded.Available, Balances: make([]BalanceInfo, 0, len(decoded.Balances)), CheckedAt: time.Now()}
	for _, item := range decoded.Balances {
		result.Balances = append(result.Balances, BalanceInfo{
			Currency: item.Currency, TotalBalance: item.TotalBalance,
			GrantedBalance: item.GrantedBalance, ToppedUpBalance: item.ToppedUpBalance,
		})
	}
	return result, nil
}

func (s *Service) Analyze(ctx context.Context, in Request) (Result, error) {
	if in.ApplicationID < 1 {
		return Result{}, errors.New("请选择需要分析的投递")
	}
	application, err := s.store.GetApplication(ctx, in.ApplicationID)
	if err != nil {
		return Result{}, err
	}
	profile, err := s.store.GetProfile(ctx)
	if err != nil {
		return Result{}, err
	}
	materials, err := s.store.ListMaterials(ctx)
	if err != nil {
		return Result{}, err
	}
	systemPrompt, userPrompt, err := buildPrompt(in.Kind, application, profile, materials, in.ExtraContext)
	if err != nil {
		return Result{}, err
	}
	started := time.Now()
	cfg := s.settings.Get().AI
	if cfg.Mode == "reasonix" {
		content, model, err := s.analyzeReasonix(ctx, cfg, systemPrompt+"\n\n"+userPrompt)
		if err != nil {
			return Result{}, err
		}
		return normalizeResult("reasonix", model, content, time.Since(started)), nil
	}
	content, err := s.analyzeDirect(ctx, cfg, systemPrompt, userPrompt)
	if err != nil {
		return Result{}, err
	}
	return normalizeResult("deepseek", cfg.Model, content, time.Since(started)), nil
}

func (s *Service) analyzeDirect(ctx context.Context, cfg settings.AIConfig, systemPrompt, userPrompt string) (string, error) {
	key := strings.TrimSpace(os.Getenv("DEEPSEEK_API_KEY"))
	if key == "" {
		return "", errors.New("尚未配置 DeepSeek API Key")
	}
	endpoint, err := joinEndpoint(cfg.BaseURL, "chat/completions")
	if err != nil {
		return "", err
	}
	payload := map[string]any{
		"model":           cfg.Model,
		"messages":        []map[string]string{{"role": "system", "content": systemPrompt}, {"role": "user", "content": userPrompt}},
		"response_format": map[string]string{"type": "json_object"},
		"max_tokens":      3000,
		"stream":          false,
		"thinking":        map[string]string{"type": map[bool]string{true: "enabled", false: "disabled"}[cfg.Thinking]},
	}
	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "ResumeDetective/4")
	resp, err := s.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("DeepSeek 请求失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", apiStatusError(resp)
	}
	var decoded struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxResponseBytes)).Decode(&decoded); err != nil {
		return "", errors.New("DeepSeek 返回内容无法解析")
	}
	if len(decoded.Choices) == 0 || strings.TrimSpace(decoded.Choices[0].Message.Content) == "" {
		return "", errors.New("DeepSeek 返回了空结果，请稍后重试")
	}
	return decoded.Choices[0].Message.Content, nil
}

func (s *Service) analyzeReasonix(ctx context.Context, cfg settings.AIConfig, prompt string) (string, string, error) {
	path, err := validateReasonix(cfg.ReasonixPath)
	if err != nil {
		return "", "", err
	}
	args := []string{"-p", prompt, "--output-format", "json", "--max-steps", "1", "--permission-mode", "dontask"}
	if strings.TrimSpace(cfg.Model) != "" {
		args = append(args, "--model", cfg.Model)
	}
	cmd := exec.CommandContext(ctx, path, args...)
	cmd.Dir = s.workDir
	cmd.Env = os.Environ()
	output, err := cmd.Output()
	if err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			message := strings.TrimSpace(string(exit.Stderr))
			if len(message) > 500 {
				message = message[:500]
			}
			return "", "", fmt.Errorf("Reasonix 分析失败: %s", message)
		}
		return "", "", fmt.Errorf("Reasonix 分析失败: %w", err)
	}
	if len(output) > maxResponseBytes {
		return "", "", errors.New("Reasonix 返回内容过大")
	}
	var result struct {
		IsError bool   `json:"is_error"`
		Result  string `json:"result"`
	}
	if err := json.Unmarshal(output, &result); err != nil {
		return "", "", errors.New("Reasonix 返回格式不兼容，请检查版本")
	}
	if result.IsError || strings.TrimSpace(result.Result) == "" {
		return "", "", errors.New("Reasonix 未返回有效结果")
	}
	return result.Result, cfg.Model, nil
}

func buildPrompt(kind string, app store.Application, profile store.Profile, materials []store.Material, extra string) (string, string, error) {
	base := "你是中国大陆校园招聘求职助手。只依据用户给出的真实信息进行分析，不得编造经历、技能、公司流程或薪资。输出必须是一个合法 json 对象，不要使用 Markdown 代码围栏。"
	var instruction string
	switch kind {
	case "job_match":
		instruction = `输出结构：{"score":0到100的整数,"summary":"一句话结论","matched":["已有证据"],"gaps":["缺口"],"actions":["下一步"],"risks":["可能被追问的风险"]}`
	case "resume_suggestions":
		instruction = `输出结构：{"summary":"总体建议","suggestions":[{"area":"位置","before":"仅在已提供原文时填写","after":"不虚构事实的改写建议","reason":"原因"}],"keywords":["可自然补充的JD关键词"],"questions":["需要用户补充确认的事实"]}`
	case "interview_prep":
		instruction = `输出结构：{"focus":["重点准备"],"technical":["技术或业务问题"],"projectQuestions":["项目追问"],"companyQuestions":["反问问题"],"plan":["按优先级排列的准备动作"]}`
	default:
		return "", "", errors.New("不支持的 AI 分析类型")
	}
	contextText := buildCandidateContext(profile, materials)
	user := fmt.Sprintf("公司：%s\n岗位：%s\n城市：%s\n岗位方向：%s\n标签：%s\n当前阶段：%s（%s）\n投递来源：%s\nJD 原文：\n%s\n\n已保存的候选人资料与真实经历：\n%s\n\n本次补充信息：\n%s", app.CompanyName, app.PositionName, app.City, app.Category, app.Tags, app.CurrentStatus, app.StageState, app.Source, app.JDText, contextText, strings.TrimSpace(extra))
	return base + "\n" + instruction, user, nil
}

func buildCandidateContext(profile store.Profile, materials []store.Material) string {
	var b strings.Builder
	fmt.Fprintf(&b, "姓名：%s\n学历：%s\n学校：%s\n专业：%s\n所在城市：%s\n目标方向：%s\n个人概述：%s\nGitHub：%s\n作品集：%s\n",
		profile.FullName, profile.Education, profile.School, profile.Major, profile.City, profile.TargetRole, profile.Summary, profile.GitHubURL, profile.PortfolioURL)
	for _, item := range materials {
		if b.Len() >= 30000 {
			break
		}
		fmt.Fprintf(&b, "\n[%s] %s（%s 至 %s；标签：%s）\n%s\n", item.MaterialType, item.Title, item.StartTime, item.EndTime, item.Tags, item.Content)
	}
	text := strings.TrimSpace(b.String())
	if text == "" {
		return "（尚未建立资料库；仅依据 JD 与本次补充信息分析）"
	}
	if len(text) > 32000 {
		text = text[:32000] + "\n（其余经历因长度限制未发送）"
	}
	return text
}

func normalizeResult(provider, model, raw string, duration time.Duration) Result {
	trimmed := strings.TrimSpace(raw)
	var content any
	if json.Unmarshal([]byte(trimmed), &content) != nil {
		content = map[string]any{"summary": trimmed}
	}
	return Result{Provider: provider, Model: model, Content: content, Raw: trimmed, Duration: duration.Milliseconds()}
}

func joinEndpoint(baseURL, suffix string) (string, error) {
	u, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil {
		return "", errors.New("AI 接口地址必须是有效的 HTTPS 地址")
	}
	u.Path = strings.TrimRight(u.Path, "/") + "/" + strings.TrimLeft(suffix, "/")
	return u.String(), nil
}

func validateReasonix(path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", errors.New("请先选择 Reasonix CLI")
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	info, err := os.Stat(abs)
	if err != nil || !info.Mode().IsRegular() {
		return "", errors.New("Reasonix CLI 文件不存在")
	}
	name := strings.ToLower(filepath.Base(abs))
	if name != "reasonix.exe" && name != "reasonix" {
		return "", errors.New("请选择 reasonix.exe")
	}
	return abs, nil
}

func apiStatusError(resp *http.Response) error {
	message := ""
	var payload struct {
		Error struct {
			Message string `json:"message"`
		} `json:"error"`
	}
	_ = json.NewDecoder(io.LimitReader(resp.Body, 256<<10)).Decode(&payload)
	message = strings.TrimSpace(payload.Error.Message)
	if message == "" {
		message = resp.Status
	}
	if len(message) > 500 {
		message = message[:500]
	}
	return fmt.Errorf("AI 服务返回错误（%d）：%s", resp.StatusCode, message)
}
