#!/usr/bin/env bash
# lib-truncate.sh — Output truncation utilities
#
# Provides 40/60 head/tail truncation for command output.
# When output exceeds a limit, keeps first 40% (error messages appear early)
# and last 60% (most recent/relevant output).
#
# Usage:
#   source lib-truncate.sh
#   truncated=$(echo "$long_output" | truncate_head_tail 50000)
#   truncated_lines=$(echo "$long_output" | truncate_head_tail_lines 200)

# truncate_head_tail MAX_CHARS
# Reads stdin, truncates to MAX_CHARS using 40/60 head/tail split.
# If input is within limit, passes through unchanged.
truncate_head_tail() {
    local max_chars="${1:-50000}"
    local input
    input=$(cat)

    local len=${#input}
    if (( len <= max_chars )); then
        printf '%s' "$input"
        return 0
    fi

    local head_chars=$(( max_chars * 2 / 5 ))  # 40%
    local tail_chars=$(( max_chars - head_chars ))  # 60%
    local omitted=$(( len - head_chars - tail_chars ))

    printf '%s' "${input:0:$head_chars}"
    printf '\n\n... [OUTPUT TRUNCATED — %d chars omitted out of %d total] ...\n\n' "$omitted" "$len"
    printf '%s' "${input: -$tail_chars}"
}

# truncate_head_tail_lines MAX_LINES
# Reads stdin, truncates to MAX_LINES using 40/60 head/tail split by line count.
truncate_head_tail_lines() {
    local max_lines="${1:-200}"
    local input
    input=$(cat)

    local total_lines
    total_lines=$(echo "$input" | wc -l)

    if (( total_lines <= max_lines )); then
        printf '%s' "$input"
        return 0
    fi

    local head_lines=$(( max_lines * 2 / 5 ))  # 40%
    local tail_lines=$(( max_lines - head_lines ))  # 60%
    local omitted=$(( total_lines - head_lines - tail_lines ))

    echo "$input" | head -n "$head_lines"
    printf '\n... [%d lines omitted out of %d total] ...\n\n' "$omitted" "$total_lines"
    echo "$input" | tail -n "$tail_lines"
}
