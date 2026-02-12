---
name: smoke-test
description: Run smoke tests against a running app — detect dev server, walk critical user journeys, report results
argument-hint: "[URL or port, e.g. http://localhost:3000 or 8080]"
---

# /smoke-test

Quick end-to-end smoke test: detect the running app, walk through critical user journeys, and report pass/fail with screenshots.

## Input

<smoke_test_input> #$ARGUMENTS </smoke_test_input>

## Step 1: Detect the App

Resolve what we're testing:

1. **If argument is a URL** → use it directly
2. **If argument is a port number** → use `http://localhost:<port>`
3. **If no argument** → auto-detect:
   ```bash
   # Check common dev server ports
   for port in 3000 3001 5173 5174 4321 8000 8080 8888; do
     curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" 2>/dev/null | grep -q "200\|301\|302" && echo "Found: http://localhost:$port"
   done
   ```
4. **If nothing found** → check if this is a TUI app (look for main.go, Cargo.toml with terminal deps, etc.) and use TUI Vision instead

Report what was detected before proceeding.

## Step 2: Find User Journeys

Look for acceptance criteria to test:

1. Check `docs/prds/*.md` for acceptance criteria (most recent PRD)
2. Check `docs/plans/*.md` for test scenarios (most recent plan)
3. Check `README.md` for usage examples
4. If nothing found → infer 3-5 basic journeys from the app (load homepage, navigate, submit form, etc.)

List the journeys you'll test and proceed.

## Step 3: Run Smoke Tests

For **web apps** — use the `webapp-testing` skill if available, otherwise use `WebFetch` on each URL:

- Load the main page — verify it returns 200 and contains expected content
- Navigate to each key route — verify no 500s or blank pages
- For forms: check that required fields and submit buttons exist
- For APIs: hit key endpoints and verify response shape

For **TUI apps** — use TUI Vision (`tuivision` MCP tools):

- Spawn the app with `spawn_tui`
- Take a screenshot with `get_screenshot` to verify initial render
- Send key inputs to navigate through primary flows
- Verify expected text appears with `wait_for_text`
- Close the session

For each journey, record: **pass/fail**, what was checked, and any error details.

## Step 4: Report Results

```
Smoke Test Results
==================
App: <URL or binary>
Journeys tested: <N>

✓ <journey 1> — <what was verified>
✓ <journey 2> — <what was verified>
✗ <journey 3> — <error details>

Result: <N>/<total> passed
```

If any journey fails, provide actionable details (HTTP status, missing element, error message).

## Integration

This command is called automatically by `/work` after execution completes (when a dev server is detectable). It can also be run standalone at any time.
