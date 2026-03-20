module github.com/mistakeknot/clavain-cli

go 1.22

require (
	github.com/mistakeknot/intercore v0.0.0-00010101000000-000000000000
	github.com/strongdm/ai-cxdb/clients/go v0.0.0
	github.com/vmihailenco/msgpack/v5 v5.4.1
	github.com/zeebo/blake3 v0.2.4
	gopkg.in/yaml.v3 v3.0.1
	modernc.org/sqlite v1.29.0
)

require (
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/hashicorp/golang-lru/v2 v2.0.7 // indirect
	github.com/klauspost/cpuid/v2 v2.2.3 // indirect
	github.com/mattn/go-isatty v0.0.16 // indirect
	github.com/ncruces/go-strftime v0.1.9 // indirect
	github.com/remyoudompheng/bigfft v0.0.0-20230129092748-24d4a6f8daec // indirect
	github.com/vmihailenco/tagparser/v2 v2.0.0 // indirect
	golang.org/x/sys v0.16.0 // indirect
	modernc.org/gc/v3 v3.0.0-20240107210532-573471604cb6 // indirect
	modernc.org/libc v1.41.0 // indirect
	modernc.org/mathutil v1.6.0 // indirect
	modernc.org/memory v1.7.2 // indirect
	modernc.org/strutil v1.2.0 // indirect
	modernc.org/token v1.1.0 // indirect
)

replace github.com/strongdm/ai-cxdb/clients/go => ../../vendor-src/cxdb/clients/go

replace github.com/mistakeknot/intercore => ../../vendor-src/intercore
