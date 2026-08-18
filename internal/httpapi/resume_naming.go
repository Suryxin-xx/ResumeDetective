package httpapi

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode"

	"github.com/Suryxin-xx/ResumeDetective/internal/settings"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

var unsafeResumeChars = regexp.MustCompile(`[<>:"/\\|?*]+`)
var resumeWhitespace = regexp.MustCompile(`\s+`)

func sanitizeResumeName(value string) string {
	value = strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return -1
		}
		return r
	}, value)
	value = unsafeResumeChars.ReplaceAllString(value, "-")
	value = resumeWhitespace.ReplaceAllString(strings.TrimSpace(value), " ")
	value = strings.Trim(value, ". ")
	for strings.Contains(value, "--") {
		value = strings.ReplaceAll(value, "--", "-")
	}
	runes := []rune(value)
	if len(runes) > 120 {
		value = string(runes[:120])
	}
	return strings.Trim(value, ". -")
}

func renderResumeName(template string, app store.Application, now time.Time) string {
	if strings.TrimSpace(template) == "" {
		template = settings.DefaultResumeNameTemplate
	}
	date := strings.TrimSpace(app.AppliedAt)
	if date == "" {
		date = now.Format("2006-01-02")
	}
	replacer := strings.NewReplacer(
		"{company}", app.CompanyName,
		"{position}", app.PositionName,
		"{category}", app.Category,
		"{date}", date,
	)
	result := sanitizeResumeName(replacer.Replace(template))
	if result == "" || strings.Contains(result, "{") || strings.Contains(result, "}") {
		result = sanitizeResumeName(app.CompanyName + "-" + app.PositionName)
	}
	if result == "" {
		return "resume"
	}
	return result
}

func availableResumePath(directory, baseName, extension, current string) (string, error) {
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return "", err
	}
	baseName = sanitizeResumeName(baseName)
	if baseName == "" {
		baseName = "resume"
	}
	if extension == "" {
		extension = ".pdf"
	}
	for suffix := 0; suffix < 10_000; suffix++ {
		name := baseName
		if suffix > 0 {
			name = fmt.Sprintf("%s-%d", baseName, suffix+1)
		}
		candidate := filepath.Join(directory, name+extension)
		if current != "" && strings.EqualFold(filepath.Clean(candidate), filepath.Clean(current)) {
			return candidate, nil
		}
		if _, err := os.Stat(candidate); os.IsNotExist(err) {
			return candidate, nil
		} else if err != nil {
			return "", err
		}
	}
	return "", fmt.Errorf("无法生成不重复的简历文件名")
}

func pathInsideDirectory(directory, candidate string) bool {
	root, err := filepath.Abs(directory)
	if err != nil {
		return false
	}
	path, err := filepath.Abs(candidate)
	if err != nil {
		return false
	}
	relative, err := filepath.Rel(root, path)
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) && !filepath.IsAbs(relative)
}
