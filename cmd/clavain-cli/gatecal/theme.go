package gatecal

import "strings"

var knownPrefixes = map[string]string{
	"safety_":  "safety",
	"quality_": "quality",
	"perf_":    "perf",
}

// DeriveTheme returns (theme, theme_source) for a given check_type.
func DeriveTheme(checkType string, bdStateFn func(string) (string, bool)) (theme, source string) {
	if bdStateFn != nil {
		if v, ok := bdStateFn(checkType); ok && v != "" {
			return v, "labeled"
		}
	}
	for prefix, inferredTheme := range knownPrefixes {
		if strings.HasPrefix(checkType, prefix) {
			return inferredTheme, "inferred"
		}
	}
	return "default", "default"
}
