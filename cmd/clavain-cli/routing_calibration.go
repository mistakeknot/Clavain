package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"math/big"
	"strconv"
	"strings"
)

type exactAgentCalibration struct {
	recommendedModel    *string
	currentModel        *string
	hitRate             *big.Rat
	weightedHitRate     *big.Rat
	confidence          *big.Rat
	evidenceSessions    *big.Rat
	propagationEligible *bool
	reason              *string
	phases              map[string]exactAgentCalibration
}

func parseInterspectCalibration(data []byte) (*InterspectCalibration, error) {
	root, err := decodeStrictCalibrationJSON(data)
	if err != nil {
		return nil, err
	}
	obj, ok := root.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("top level must be an object")
	}
	schema, err := exactCalibrationInteger(obj["schema_version"])
	if err != nil || (schema != 1 && schema != 2 && schema != 3) {
		return nil, fmt.Errorf("schema_version must be an integral supported version")
	}
	cal := &InterspectCalibration{
		SchemaVersion: schema,
		Agents:        map[string]AgentCalibration{},
		exactAgents:   map[string]exactAgentCalibration{},
		fileBacked:    true,
	}
	if value, ok := obj["calibrated_at"].(string); ok {
		cal.CalibratedAt = value
	}
	if value, err := exactCalibrationInteger(obj["min_sessions"]); err == nil {
		cal.MinSessions = value
	}
	if value, err := exactCalibrationInteger(obj["min_non_bootstrap_sessions"]); err == nil {
		cal.MinNonBootstrapSessions = value
	}
	if weights, ok := obj["source_weights"].(map[string]any); ok {
		cal.SourceWeights = map[string]float64{}
		for name, rawWeight := range weights {
			if exact, ok := rawWeight.(*big.Rat); ok {
				cal.SourceWeights[name], _ = exact.Float64()
			}
		}
	}
	if rawAgents, exists := obj["agents"]; exists {
		agents, ok := rawAgents.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("agents must be an object")
		}
		for name, rawEntry := range agents {
			exact, err := parseExactAgentCalibration(rawEntry, true)
			if err != nil {
				return nil, fmt.Errorf("agent %s: %w", name, err)
			}
			cal.exactAgents[name] = exact
			cal.Agents[name] = publicAgentCalibration(exact)
		}
	}
	return cal, nil
}

func parseExactAgentCalibration(value any, allowPhases bool) (exactAgentCalibration, error) {
	obj, ok := value.(map[string]any)
	if !ok {
		return exactAgentCalibration{}, fmt.Errorf("entry must be an object")
	}
	entry := exactAgentCalibration{phases: map[string]exactAgentCalibration{}}
	if value, exists := obj["recommended_model"]; exists {
		model, ok := value.(string)
		if !ok {
			return entry, fmt.Errorf("recommended_model must be a string")
		}
		entry.recommendedModel = &model
	}
	if value, ok := obj["current_model"].(string); ok {
		entry.currentModel = &value
	}
	for field, target := range map[string]**big.Rat{
		"confidence":        &entry.confidence,
		"evidence_sessions": &entry.evidenceSessions,
	} {
		if value, exists := obj[field]; exists {
			number, ok := value.(*big.Rat)
			if !ok {
				return entry, fmt.Errorf("%s must be a number", field)
			}
			*target = new(big.Rat).Set(number)
		}
	}
	if value, ok := obj["hit_rate"].(*big.Rat); ok {
		entry.hitRate = new(big.Rat).Set(value)
	}
	if value, ok := obj["weighted_hit_rate"].(*big.Rat); ok {
		entry.weightedHitRate = new(big.Rat).Set(value)
	}
	if value, exists := obj["propagation_eligible"]; exists {
		eligible, ok := value.(bool)
		if !ok {
			return entry, fmt.Errorf("propagation_eligible must be a boolean")
		}
		entry.propagationEligible = &eligible
	}
	if value, ok := obj["reason"].(string); ok {
		entry.reason = &value
	}
	if value, exists := obj["phases"]; exists {
		phases, ok := value.(map[string]any)
		if !allowPhases || !ok {
			return entry, fmt.Errorf("phases must be an object and cannot be nested")
		}
		for phase, rawPhase := range phases {
			parsed, err := parseExactAgentCalibration(rawPhase, false)
			if err != nil {
				return entry, fmt.Errorf("phase %s: %w", phase, err)
			}
			entry.phases[phase] = parsed
		}
	}
	return entry, nil
}

func publicAgentCalibration(exact exactAgentCalibration) AgentCalibration {
	result := AgentCalibration{Phases: map[string]AgentCalibration{}}
	if exact.recommendedModel != nil {
		result.RecommendedModel = *exact.recommendedModel
	}
	if exact.currentModel != nil {
		result.CurrentModel = *exact.currentModel
	}
	if exact.hitRate != nil {
		result.HitRate, _ = exact.hitRate.Float64()
	}
	if exact.weightedHitRate != nil {
		result.WeightedHitRate, _ = exact.weightedHitRate.Float64()
	}
	if exact.confidence != nil {
		result.Confidence, _ = exact.confidence.Float64()
	}
	if exact.evidenceSessions != nil && exact.evidenceSessions.IsInt() && exact.evidenceSessions.Num().IsInt64() {
		value := exact.evidenceSessions.Num().Int64()
		if int64(int(value)) == value {
			result.EvidenceSessions = int(value)
		}
	}
	if exact.propagationEligible != nil {
		result.PropagationEligible = *exact.propagationEligible
	}
	if exact.reason != nil {
		result.Reason = *exact.reason
	}
	for phase, entry := range exact.phases {
		result.Phases[phase] = publicAgentCalibration(entry)
	}
	return result
}

func exactCalibrationInteger(value any) (int, error) {
	number, ok := value.(*big.Rat)
	if !ok || !number.IsInt() || !number.Num().IsInt64() {
		return 0, fmt.Errorf("not an integral number")
	}
	value64 := number.Num().Int64()
	if int64(int(value64)) != value64 {
		return 0, fmt.Errorf("number outside int range")
	}
	return int(value64), nil
}

func decodeStrictCalibrationJSON(data []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	value, err := decodeCalibrationValue(decoder)
	if err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		return nil, fmt.Errorf("trailing JSON")
	}
	return value, nil
}

func decodeCalibrationValue(decoder *json.Decoder) (any, error) {
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	switch value := token.(type) {
	case json.Delim:
		switch value {
		case '{':
			obj := map[string]any{}
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return nil, err
				}
				key, ok := keyToken.(string)
				if !ok {
					return nil, fmt.Errorf("object key must be a string")
				}
				if _, exists := obj[key]; exists {
					return nil, fmt.Errorf("duplicate key %q", key)
				}
				child, err := decodeCalibrationValue(decoder)
				if err != nil {
					return nil, err
				}
				obj[key] = child
			}
			if end, err := decoder.Token(); err != nil || end != json.Delim('}') {
				return nil, fmt.Errorf("unterminated object")
			}
			return obj, nil
		case '[':
			var result []any
			for decoder.More() {
				child, err := decodeCalibrationValue(decoder)
				if err != nil {
					return nil, err
				}
				result = append(result, child)
			}
			if end, err := decoder.Token(); err != nil || end != json.Delim(']') {
				return nil, fmt.Errorf("unterminated array")
			}
			return result, nil
		}
	case json.Number:
		raw := value.String()
		approximate, err := strconv.ParseFloat(raw, 64)
		if err != nil || math.IsInf(approximate, 0) || math.IsNaN(approximate) {
			return nil, fmt.Errorf("number outside finite range")
		}
		if approximate == 0 {
			mantissa := raw
			if i := strings.IndexAny(raw, "eE"); i >= 0 {
				mantissa = raw[:i]
			}
			if strings.ContainsAny(mantissa, "123456789") {
				return nil, fmt.Errorf("numeric underflow")
			}
			// Match Intercore without allocating an exponent-sized denominator.
			return big.NewRat(0, 1), nil
		}
		exact, ok := new(big.Rat).SetString(raw)
		if !ok {
			return nil, fmt.Errorf("invalid number")
		}
		if approximate == 0 && exact.Sign() != 0 {
			return nil, fmt.Errorf("numeric underflow")
		}
		return exact, nil
	}
	return token, nil
}

func exactCalibrationUsable(entry exactAgentCalibration, threshold *big.Rat, schema int) bool {
	if entry.recommendedModel == nil || (*entry.recommendedModel != "haiku" && *entry.recommendedModel != "sonnet" && *entry.recommendedModel != "opus") {
		return false
	}
	if entry.confidence == nil || entry.confidence.Cmp(threshold) < 0 || entry.confidence.Cmp(big.NewRat(1, 1)) > 0 {
		return false
	}
	if entry.evidenceSessions == nil || !entry.evidenceSessions.IsInt() || entry.evidenceSessions.Cmp(big.NewRat(3, 1)) < 0 {
		return false
	}
	return schema == 1 || (entry.propagationEligible != nil && *entry.propagationEligible)
}

func exactThreshold(value float64) *big.Rat {
	raw := strconv.FormatFloat(value, 'g', -1, 64)
	threshold, ok := new(big.Rat).SetString(raw)
	if !ok {
		return big.NewRat(7, 10)
	}
	return threshold
}

func exactCalibrationCandidate(cal *InterspectCalibration, agentID, stage string, threshold float64) (string, bool) {
	if agentID == "" || strings.HasSuffix(agentID, ":") || math.IsNaN(threshold) || math.IsInf(threshold, 0) {
		return "", false
	}
	entry, ok := cal.exactAgents[agentID]
	if !ok && strings.Contains(agentID, ":") {
		entry, ok = cal.exactAgents[agentID[strings.LastIndex(agentID, ":")+1:]]
	}
	if !ok {
		return "", false
	}
	exactLimit := exactThreshold(threshold)
	for _, phase := range phaseCalibrationKeys(stage) {
		if candidate, exists := entry.phases[phase]; exists && exactCalibrationUsable(candidate, exactLimit, cal.SchemaVersion) {
			return *candidate.recommendedModel, true
		}
	}
	if exactCalibrationUsable(entry, exactLimit, cal.SchemaVersion) {
		return *entry.recommendedModel, true
	}
	return "", false
}
