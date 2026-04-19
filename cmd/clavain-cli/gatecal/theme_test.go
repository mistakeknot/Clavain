package gatecal

import "testing"

func TestDeriveTheme(t *testing.T) {
	cases := []struct {
		name       string
		checkType  string
		bdStateVal string
		bdStateOK  bool
		wantTheme  string
		wantSource string
	}{
		{"labeled wins", "safety_secrets", "compliance", true, "compliance", "labeled"},
		{"inferred prefix safety_", "safety_secrets", "", false, "safety", "inferred"},
		{"inferred prefix quality_", "quality_test_pass", "", false, "quality", "inferred"},
		{"inferred prefix perf_", "perf_p99_latency", "", false, "perf", "inferred"},
		{"default fallback", "random_check", "", false, "default", "default"},
		{"empty check defaults", "", "", false, "default", "default"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			fn := func(string) (string, bool) { return c.bdStateVal, c.bdStateOK }
			theme, src := DeriveTheme(c.checkType, fn)
			if theme != c.wantTheme || src != c.wantSource {
				t.Errorf("DeriveTheme(%q) = (%q,%q), want (%q,%q)",
					c.checkType, theme, src, c.wantTheme, c.wantSource)
			}
		})
	}
}
