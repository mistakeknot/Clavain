package gatecal

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"
)

// v1File mirrors the legacy gate calibration JSON format.
type v1File struct {
	CreatedAt int64             `json:"created_at"`
	SinceID   int64             `json:"since_id"`
	Tiers     map[string]v1Entry `json:"tiers"`
}

type v1Entry struct {
	Tier           string  `json:"tier"`
	Locked         bool    `json:"locked"`
	FPR            float64 `json:"fpr"`
	FNR            float64 `json:"fnr"`
	WeightedN      float64 `json:"weighted_n"`
	LastChangedAt  int64   `json:"last_changed_at,omitempty"`
	ChangeCount90d int     `json:"change_count_90d,omitempty"`
	UpdatedAt      int64   `json:"updated_at"`
}

// MigrateFromV1 imports legacy JSON entries into tier_state once, then archives
// the source file as <v1Path>.v1.json.bak.
func (s *Store) MigrateFromV1(ctx context.Context, v1Path string) error {
	var count int
	if err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM tier_state`).Scan(&count); err != nil {
		return fmt.Errorf("gatecal.migrate: count tier_state: %w", err)
	}
	if count > 0 {
		return nil
	}

	data, err := os.ReadFile(v1Path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return fmt.Errorf("gatecal.migrate: read %s: %w", v1Path, err)
	}

	var v1 v1File
	if err := json.Unmarshal(data, &v1); err != nil {
		return fmt.Errorf("gatecal.migrate: parse v1 JSON: %w", err)
	}

	if len(v1.Tiers) == 0 {
		if err := os.Rename(v1Path, v1Path+".v1.json.bak"); err != nil {
			return fmt.Errorf("gatecal.migrate: archive %s: %w", v1Path, err)
		}
		return nil
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("gatecal.migrate: begin: %w", err)
	}
	defer tx.Rollback()

	now := time.Now().Unix()
	for key, entry := range v1.Tiers {
		checkType, phaseFrom, phaseTo, ok := splitV1Key(key)
		if !ok {
			return fmt.Errorf("gatecal.migrate: malformed v1 key %q", key)
		}

		locked := 0
		if entry.Locked {
			locked = 1
		}

		_, err := tx.ExecContext(ctx, `
INSERT INTO tier_state (theme, check_type, phase_from, phase_to, tier, fpr, fnr, weighted_n, locked, change_count_90d, last_changed_at, origin_key, theme_source, updated_at)
VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULLIF(?, 0), ?, 'migrated', ?)`,
			checkType, phaseFrom, phaseTo, entry.Tier, entry.FPR, entry.FNR, entry.WeightedN,
			locked, entry.ChangeCount90d, entry.LastChangedAt, key, now,
		)
		if err != nil {
			return fmt.Errorf("gatecal.migrate: insert %q: %w", key, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("gatecal.migrate: commit: %w", err)
	}

	if err := os.Rename(v1Path, v1Path+".v1.json.bak"); err != nil {
		return fmt.Errorf("gatecal.migrate: archive %s: %w", v1Path, err)
	}
	return nil
}

func splitV1Key(key string) (checkType, phaseFrom, phaseTo string, ok bool) {
	parts := strings.SplitN(key, "|", 3)
	if len(parts) != 3 {
		return "", "", "", false
	}
	return parts[0], parts[1], parts[2], true
}
