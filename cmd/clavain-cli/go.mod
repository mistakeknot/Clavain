module github.com/mistakeknot/clavain-cli

go 1.22

require (
	github.com/strongdm/ai-cxdb/clients/go v0.0.0
	github.com/vmihailenco/msgpack/v5 v5.4.1
	gopkg.in/yaml.v3 v3.0.1
)

require (
	github.com/klauspost/cpuid/v2 v2.0.12 // indirect
	github.com/vmihailenco/tagparser/v2 v2.0.0 // indirect
	github.com/zeebo/blake3 v0.2.4 // indirect
)

replace github.com/strongdm/ai-cxdb/clients/go => ../../vendor-src/cxdb/clients/go
