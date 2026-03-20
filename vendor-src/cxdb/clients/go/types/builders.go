// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package types

// =============================================================================
// Context Metadata Helpers
// =============================================================================

// WithContextMetadata attaches context metadata to any ConversationItem.
// By convention, this should only be used on the first turn of a context.
func (item *ConversationItem) WithContextMetadata(meta *ContextMetadata) *ConversationItem {
	item.ContextMetadata = meta
	return item
}

// WithClientTag is a convenience method to attach just a client tag.
// By convention, this should only be used on the first turn of a context.
func (item *ConversationItem) WithClientTag(tag string) *ConversationItem {
	if item.ContextMetadata == nil {
		item.ContextMetadata = &ContextMetadata{}
	}
	item.ContextMetadata.ClientTag = tag
	return item
}

// =============================================================================
// User Input Builders
// =============================================================================

// NewUserInput creates a user input conversation item.
func NewUserInput(text string, files ...string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeUserInput,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		UserInput: &UserInput{
			Text:  text,
			Files: files,
		},
	}
}

// =============================================================================
// Assistant Turn Builders (v2 - preferred)
// =============================================================================

// NewAssistantTurn creates an assistant turn conversation item.
func NewAssistantTurn(text string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeAssistantTurn,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		Turn: &AssistantTurn{
			Text: text,
		},
	}
}

// AssistantTurnBuilder provides fluent configuration for assistant turn items.
type AssistantTurnBuilder struct {
	item *ConversationItem
}

// BuildAssistantTurn starts building an assistant turn conversation item.
func BuildAssistantTurn(text string) *AssistantTurnBuilder {
	return &AssistantTurnBuilder{
		item: &ConversationItem{
			ItemType:  ItemTypeAssistantTurn,
			Status:    ItemStatusComplete,
			Timestamp: Now(),
			Turn: &AssistantTurn{
				Text:      text,
				ToolCalls: make([]ToolCallItem, 0),
			},
		},
	}
}

// WithReasoning adds reasoning/thinking content.
func (b *AssistantTurnBuilder) WithReasoning(reasoning string) *AssistantTurnBuilder {
	b.item.Turn.Reasoning = reasoning
	return b
}

// WithAgent sets the agent name.
func (b *AssistantTurnBuilder) WithAgent(agent string) *AssistantTurnBuilder {
	b.item.Turn.Agent = agent
	return b
}

// WithTurnNumber sets the turn number and optionally max turns.
func (b *AssistantTurnBuilder) WithTurnNumber(turn, maxTurns int) *AssistantTurnBuilder {
	b.item.Turn.TurnNumber = turn
	b.item.Turn.MaxTurns = maxTurns
	return b
}

// WithFinishReason sets the finish reason.
func (b *AssistantTurnBuilder) WithFinishReason(reason string) *AssistantTurnBuilder {
	b.item.Turn.FinishReason = reason
	return b
}

// WithMetrics sets token usage metrics.
func (b *AssistantTurnBuilder) WithMetrics(inputTokens, outputTokens int64) *AssistantTurnBuilder {
	b.item.Turn.Metrics = &TurnMetrics{
		InputTokens:  inputTokens,
		OutputTokens: outputTokens,
		TotalTokens:  inputTokens + outputTokens,
	}
	return b
}

// WithFullMetrics sets complete token usage metrics.
func (b *AssistantTurnBuilder) WithFullMetrics(metrics *TurnMetrics) *AssistantTurnBuilder {
	b.item.Turn.Metrics = metrics
	return b
}

// WithToolCall adds a tool call to the turn.
func (b *AssistantTurnBuilder) WithToolCall(tc ToolCallItem) *AssistantTurnBuilder {
	b.item.Turn.ToolCalls = append(b.item.Turn.ToolCalls, tc)
	return b
}

// WithStatus sets the item status.
func (b *AssistantTurnBuilder) WithStatus(status ItemStatus) *AssistantTurnBuilder {
	b.item.Status = status
	return b
}

// WithID sets the item ID.
func (b *AssistantTurnBuilder) WithID(id string) *AssistantTurnBuilder {
	b.item.ID = id
	return b
}

// WithContextMetadata attaches context metadata (for first turn only).
func (b *AssistantTurnBuilder) WithContextMetadata(meta *ContextMetadata) *AssistantTurnBuilder {
	b.item.ContextMetadata = meta
	return b
}

// WithClientTag attaches a client tag (for first turn only).
func (b *AssistantTurnBuilder) WithClientTag(tag string) *AssistantTurnBuilder {
	if b.item.ContextMetadata == nil {
		b.item.ContextMetadata = &ContextMetadata{}
	}
	b.item.ContextMetadata.ClientTag = tag
	return b
}

// Build returns the configured conversation item.
func (b *AssistantTurnBuilder) Build() *ConversationItem {
	return b.item
}

// =============================================================================
// Tool Call Item Builder
// =============================================================================

// NewToolCallItem creates a tool call item for embedding in an assistant turn.
func NewToolCallItem(id, name, args string) ToolCallItem {
	return ToolCallItem{
		ID:     id,
		Name:   name,
		Args:   args,
		Status: ToolCallStatusPending,
	}
}

// ToolCallItemBuilder provides fluent configuration for tool call items.
type ToolCallItemBuilder struct {
	tc ToolCallItem
}

// BuildToolCallItem starts building a tool call item.
func BuildToolCallItem(id, name, args string) *ToolCallItemBuilder {
	return &ToolCallItemBuilder{
		tc: ToolCallItem{
			ID:     id,
			Name:   name,
			Args:   args,
			Status: ToolCallStatusPending,
		},
	}
}

// WithDescription adds a human-readable description.
func (b *ToolCallItemBuilder) WithDescription(desc string) *ToolCallItemBuilder {
	b.tc.Description = desc
	return b
}

// WithStatus sets the tool call status.
func (b *ToolCallItemBuilder) WithStatus(status ToolCallStatus) *ToolCallItemBuilder {
	b.tc.Status = status
	return b
}

// WithStreamingOutput sets accumulated streaming output.
func (b *ToolCallItemBuilder) WithStreamingOutput(output string, truncated bool) *ToolCallItemBuilder {
	b.tc.StreamingOutput = output
	b.tc.StreamingOutputTruncated = truncated
	return b
}

// WithResult sets the successful result.
func (b *ToolCallItemBuilder) WithResult(content string, exitCode *int) *ToolCallItemBuilder {
	b.tc.Status = ToolCallStatusComplete
	b.tc.Result = &ToolCallResult{
		Content:  content,
		Success:  true,
		ExitCode: exitCode,
	}
	return b
}

// WithError sets the error result.
func (b *ToolCallItemBuilder) WithError(message string, exitCode *int) *ToolCallItemBuilder {
	b.tc.Status = ToolCallStatusError
	b.tc.Error = &ToolCallError{
		Message:  message,
		ExitCode: exitCode,
	}
	return b
}

// WithDuration sets the execution duration in milliseconds.
func (b *ToolCallItemBuilder) WithDuration(ms int64) *ToolCallItemBuilder {
	b.tc.DurationMs = ms
	return b
}

// Build returns the configured tool call item.
func (b *ToolCallItemBuilder) Build() ToolCallItem {
	return b.tc
}

// =============================================================================
// Handoff Builder
// =============================================================================

// NewHandoff creates a handoff conversation item.
func NewHandoff(fromAgent, toAgent string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeHandoff,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		Handoff: &HandoffInfo{
			FromAgent: fromAgent,
			ToAgent:   toAgent,
		},
	}
}

// HandoffBuilder provides fluent configuration for handoff items.
type HandoffBuilder struct {
	item *ConversationItem
}

// BuildHandoff starts building a handoff conversation item.
func BuildHandoff(fromAgent, toAgent string) *HandoffBuilder {
	return &HandoffBuilder{
		item: &ConversationItem{
			ItemType:  ItemTypeHandoff,
			Status:    ItemStatusComplete,
			Timestamp: Now(),
			Handoff: &HandoffInfo{
				FromAgent: fromAgent,
				ToAgent:   toAgent,
			},
		},
	}
}

// WithToolName sets the handoff tool name.
func (b *HandoffBuilder) WithToolName(toolName string) *HandoffBuilder {
	b.item.Handoff.ToolName = toolName
	return b
}

// WithInput sets the input passed to the target agent.
func (b *HandoffBuilder) WithInput(input string) *HandoffBuilder {
	b.item.Handoff.Input = input
	return b
}

// WithReason sets the reason for the handoff.
func (b *HandoffBuilder) WithReason(reason string) *HandoffBuilder {
	b.item.Handoff.Reason = reason
	return b
}

// WithID sets the item ID.
func (b *HandoffBuilder) WithID(id string) *HandoffBuilder {
	b.item.ID = id
	return b
}

// Build returns the configured conversation item.
func (b *HandoffBuilder) Build() *ConversationItem {
	return b.item
}

// =============================================================================
// System Message Builders
// =============================================================================

// NewSystemInfo creates an informational system message.
func NewSystemInfo(content string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeSystem,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		System: &SystemMessage{
			Kind:    SystemKindInfo,
			Content: content,
		},
	}
}

// NewSystemWarning creates a warning system message.
func NewSystemWarning(content string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeSystem,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		System: &SystemMessage{
			Kind:    SystemKindWarning,
			Content: content,
		},
	}
}

// NewSystemError creates an error system message.
func NewSystemError(content string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeSystem,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		System: &SystemMessage{
			Kind:    SystemKindError,
			Content: content,
		},
	}
}

// SystemBuilder provides fluent configuration for system message items.
type SystemBuilder struct {
	item *ConversationItem
}

// BuildSystem starts building a system message conversation item.
func BuildSystem(kind SystemKind, content string) *SystemBuilder {
	return &SystemBuilder{
		item: &ConversationItem{
			ItemType:  ItemTypeSystem,
			Status:    ItemStatusComplete,
			Timestamp: Now(),
			System: &SystemMessage{
				Kind:    kind,
				Content: content,
			},
		},
	}
}

// WithTitle adds a title to the system message.
func (b *SystemBuilder) WithTitle(title string) *SystemBuilder {
	b.item.System.Title = title
	return b
}

// WithID sets the item ID.
func (b *SystemBuilder) WithID(id string) *SystemBuilder {
	b.item.ID = id
	return b
}

// Build returns the configured conversation item.
func (b *SystemBuilder) Build() *ConversationItem {
	return b.item
}

// =============================================================================
// Legacy Builders (v1 schema - kept for backward compatibility)
// =============================================================================

// NewAssistant creates an assistant response conversation item (legacy).
// Deprecated: Use NewAssistantTurn for new code.
func NewAssistant(text string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeAssistant,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		Assistant: &Assistant{
			Text: text,
		},
	}
}

// AssistantBuilder provides fluent configuration for assistant items (legacy).
// Deprecated: Use AssistantTurnBuilder for new code.
type AssistantBuilder struct {
	item *ConversationItem
}

// BuildAssistant starts building an assistant conversation item (legacy).
// Deprecated: Use BuildAssistantTurn for new code.
func BuildAssistant(text string) *AssistantBuilder {
	return &AssistantBuilder{
		item: &ConversationItem{
			ItemType:  ItemTypeAssistant,
			Status:    ItemStatusComplete,
			Timestamp: Now(),
			Assistant: &Assistant{
				Text: text,
			},
		},
	}
}

// WithReasoning adds reasoning/thinking content.
func (b *AssistantBuilder) WithReasoning(reasoning string) *AssistantBuilder {
	b.item.Assistant.Reasoning = reasoning
	return b
}

// WithModel sets the model name.
func (b *AssistantBuilder) WithModel(model string) *AssistantBuilder {
	b.item.Assistant.Model = model
	return b
}

// WithTokens sets token usage metrics.
func (b *AssistantBuilder) WithTokens(input, output int64) *AssistantBuilder {
	b.item.Assistant.InputTokens = input
	b.item.Assistant.OutputTokens = output
	return b
}

// WithStopReason sets the stop reason.
func (b *AssistantBuilder) WithStopReason(reason string) *AssistantBuilder {
	b.item.Assistant.StopReason = reason
	return b
}

// WithStatus sets the item status.
func (b *AssistantBuilder) WithStatus(status ItemStatus) *AssistantBuilder {
	b.item.Status = status
	return b
}

// Build returns the configured conversation item.
func (b *AssistantBuilder) Build() *ConversationItem {
	return b.item
}

// NewToolCall creates a tool call conversation item (legacy).
// Deprecated: Use BuildAssistantTurn().WithToolCall() for new code.
func NewToolCall(callID, name, args string) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeToolCall,
		Status:    ItemStatusPending,
		Timestamp: Now(),
		ToolCall: &ToolCall{
			CallID: callID,
			Name:   name,
			Args:   args,
		},
	}
}

// ToolCallBuilder provides fluent configuration for tool call items (legacy).
// Deprecated: Use ToolCallItemBuilder for new code.
type ToolCallBuilder struct {
	item *ConversationItem
}

// BuildToolCall starts building a tool call conversation item (legacy).
// Deprecated: Use BuildToolCallItem for new code.
func BuildToolCall(callID, name, args string) *ToolCallBuilder {
	return &ToolCallBuilder{
		item: &ConversationItem{
			ItemType:  ItemTypeToolCall,
			Status:    ItemStatusPending,
			Timestamp: Now(),
			ToolCall: &ToolCall{
				CallID: callID,
				Name:   name,
				Args:   args,
			},
		},
	}
}

// WithDescription adds a human-readable description.
func (b *ToolCallBuilder) WithDescription(desc string) *ToolCallBuilder {
	b.item.ToolCall.Description = desc
	return b
}

// WithStatus sets the item status.
func (b *ToolCallBuilder) WithStatus(status ItemStatus) *ToolCallBuilder {
	b.item.Status = status
	return b
}

// Build returns the configured conversation item.
func (b *ToolCallBuilder) Build() *ConversationItem {
	return b.item
}

// NewToolResult creates a tool result conversation item (legacy).
// Deprecated: Use BuildAssistantTurn().WithToolCall() with Result for new code.
func NewToolResult(callID, content string, isError bool) *ConversationItem {
	return &ConversationItem{
		ItemType:  ItemTypeToolResult,
		Status:    ItemStatusComplete,
		Timestamp: Now(),
		ToolResult: &ToolResult{
			CallID:  callID,
			Content: content,
			IsError: isError,
		},
	}
}

// ToolResultBuilder provides fluent configuration for tool result items (legacy).
// Deprecated: Use ToolCallItemBuilder with WithResult/WithError for new code.
type ToolResultBuilder struct {
	item *ConversationItem
}

// BuildToolResult starts building a tool result conversation item (legacy).
// Deprecated: Use BuildToolCallItem with WithResult for new code.
func BuildToolResult(callID, content string) *ToolResultBuilder {
	return &ToolResultBuilder{
		item: &ConversationItem{
			ItemType:  ItemTypeToolResult,
			Status:    ItemStatusComplete,
			Timestamp: Now(),
			ToolResult: &ToolResult{
				CallID:  callID,
				Content: content,
				IsError: false,
			},
		},
	}
}

// WithError marks this as an error result.
func (b *ToolResultBuilder) WithError() *ToolResultBuilder {
	b.item.ToolResult.IsError = true
	return b
}

// WithExitCode sets the exit code for shell commands.
func (b *ToolResultBuilder) WithExitCode(code int) *ToolResultBuilder {
	b.item.ToolResult.ExitCode = &code
	return b
}

// WithStreamingOutput sets accumulated streaming output.
func (b *ToolResultBuilder) WithStreamingOutput(output string) *ToolResultBuilder {
	b.item.ToolResult.StreamingOutput = output
	return b
}

// WithTruncated marks the output as truncated.
func (b *ToolResultBuilder) WithTruncated() *ToolResultBuilder {
	b.item.ToolResult.OutputTruncated = true
	return b
}

// WithDuration sets the execution duration in milliseconds.
func (b *ToolResultBuilder) WithDuration(ms int64) *ToolResultBuilder {
	b.item.ToolResult.DurationMs = ms
	return b
}

// Build returns the configured conversation item.
func (b *ToolResultBuilder) Build() *ConversationItem {
	return b.item
}
