package main

import "testing"

func BenchmarkClassifyComplexityTrivial(b *testing.B) {
	desc := "rename variable foo to bar in the config file"
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = classifyComplexity(desc)
	}
}

func BenchmarkClassifyComplexityModerate(b *testing.B) {
	desc := "Add a new HTTP handler for the /api/v2/agents endpoint that returns a paginated list of active agents with their current status, context usage, and assigned tasks. The handler should support cursor-based pagination and filtering by agent type."
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = classifyComplexity(desc)
	}
}

func BenchmarkClassifyComplexityResearch(b *testing.B) {
	desc := "Explore and investigate the feasibility of replacing our current SQLite storage layer with a distributed key-value store. Research available options including etcd, TiKV, and FoundationDB. Evaluate tradeoffs between consistency models, analyze latency impact on our agent coordination protocol, and brainstorm migration strategies that preserve backward compatibility with existing data."
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = classifyComplexity(desc)
	}
}

func BenchmarkCountMatches(b *testing.B) {
	words := []string{
		"explore", "the", "feasibility", "of", "replacing", "investigate",
		"current", "storage", "layer", "research", "available", "options",
		"evaluate", "tradeoffs", "analyze", "brainstorm", "migration",
		"strategies", "compatibility", "data",
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = countMatches(words, researchKeywords)
	}
}
