package gatecal

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"
)

// ExportV1JSON regenerates legacy gate-tier-calibration.json from tier_state.
// If multiple themes map to the same v1 key, worst-case tier wins (hard > soft).
func (s *Store) ExportV1JSON(ctx context.Context, path string, sinceID int64) error {
	rows, err := s.db.QueryContext(ctx, `
SELECT check_type, phase_from, phase_to, tier, locked, fpr, fnr, weighted_n, change_count_90d, last_changed_at, updated_at
FROM tier_state
ORDER BY check_type, phase_from, phase_to,
  CASE tier WHEN 'hard' THEN 0 ELSE 1 END
`)
	if err != nil {
		return fmt.Errorf("gatecal.export: query: %w", err)
	}
	defer rows.Close()

	tiers := map[string]v1Entry{}
	for rows.Next() {
		var checkType, phaseFrom, phaseTo, tier string
		var locked int
		var fpr, fnr, weightedN float64
		var changeCount90d int
		var lastChangedAt, updatedAt int64

		if err := rows.Scan(
			&checkType,
			&phaseFrom,
			&phaseTo,
			&tier,
			&locked,
			&nullableFloat64{Dest: &fpr},
			&nullableFloat64{Dest: &fnr},
			&weightedN,
			&changeCount90d,
			&nullableInt{Dest: &lastChangedAt},
			&updatedAt,
		); err != nil {
			return fmt.Errorf("gatecal.export: scan: %w", err)
		}

		key := checkType + "|" + phaseFrom + "|" + phaseTo
		if _, exists := tiers[key]; exists {
			continue
		}
		tiers[key] = v1Entry{
			Tier:           tier,
			Locked:         locked != 0,
			FPR:            fpr,
			FNR:            fnr,
			WeightedN:      weightedN,
			LastChangedAt:  lastChangedAt,
			ChangeCount90d: changeCount90d,
			UpdatedAt:      updatedAt,
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("gatecal.export: rows: %w", err)
	}

	out := v1File{
		CreatedAt: time.Now().Unix(),
		SinceID:   sinceID,
		Tiers:     tiers,
	}
	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		return fmt.Errorf("gatecal.export: marshal: %w", err)
	}

	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return fmt.Errorf("gatecal.export: write tmp: %w", err)
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("gatecal.export: rename: %w", err)
	}
	return nil
}
