// Package secretshape detects identifier strings shaped like credentials, so
// metadata-only records can refuse them. It is a heuristic denylist layered on
// top of a strict charset and length pattern, not proof that a value is safe.
package secretshape

import "regexp"

var (
	// Well-known credential prefixes, matched at the start or after a separator.
	prefixed = regexp.MustCompile(`(?i)(^|[^a-z0-9])(gh[pousr]_|github_pat_|sk-|sk_|pk_|rk_|xox[a-z]?-?|akia|asia|aiza|glpat-|npm_|eyj)`)
	// Long unbroken alphanumeric (hex or base64-ish) runs.
	longRun = regexp.MustCompile(`[A-Za-z0-9+/=]{32,}`)
	// JWT-like: three dotted base64url segments.
	dotted = regexp.MustCompile(`^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$`)
)

// Looks reports whether v resembles a secret or token.
func Looks(v string) bool {
	return prefixed.MatchString(v) || longRun.MatchString(v) || dotted.MatchString(v)
}
