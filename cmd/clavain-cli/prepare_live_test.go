package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// Real kernel and child processes, deterministic fixture seats. This is NOT
// an actual planner/reviewer model invocation or a human acceptance canary.
func TestLivePreparationKernelPhases(t *testing.T) {
	for _, mode := range []string{"capped", "uncapped"} {
		t.Run(mode, func(t *testing.T) { testLivePreparationKernelPhases(t, mode) })
	}
}

func testLivePreparationKernelPhases(t *testing.T, mode string) {
	if os.Getenv("CLAVAIN_LIVE_REVIEW") != "1" || runtime.GOOS != "darwin" {
		t.Skip("explicit isolated kernel fixture")
	}
	base, s := ratifyFixture(t)
	if mode == "uncapped" {
		s = requestBudgetMode(t, s, `"uncapped"`, 0)
	}
	t.Setenv("PREPARE_FIXTURE_MODE", mode)
	parent, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	moved := filepath.Join(parent, "project")
	if err = os.Rename(s.Project, moved); err != nil {
		t.Fatal(err)
	}
	s.Project = moved
	s.Proposal.Project = moved
	source, _ := filepath.Abs("../..")
	policy := filepath.Join(source, "config", "routing.yaml")
	os.WriteFile(filepath.Join(s.Project, ".gitignore"), []byte(".clavain/\n"), 0600)
	reviewRun(s.Project, "git", "add", ".gitignore")
	reviewRun(s.Project, "git", "commit", "-m", "ignore fixture kernel")
	if _, err := reviewRun(parent, "ic", "init"); err != nil {
		t.Fatal(err)
	}
	fake := t.TempDir()
	os.Mkdir(filepath.Join(fake, "scripts"), 0700)
	script := filepath.Join(fake, "scripts", "dispatch.sh")
	python := filepath.Join(fake, "fixture.py")
	os.WriteFile(script, []byte("#!/bin/bash\nexec python3 "+shellReviewQuote(python)+" \"$@\"\n"), 0700)
	os.WriteFile(python, []byte(`import json,os,pathlib,subprocess,sys,hashlib
args=sys.argv[1:]
def arg(k): return args[args.index(k)+1]
db=os.environ['CLAVAIN_INTERCORE_DB'];ic=['ic','--db='+db]
os.chdir(pathlib.Path(db).parent)
role=arg('--role');out=pathlib.Path(arg('-o'));producer=arg('--producer-identity') if '--producer-identity' in args else ''
policy=os.environ['CLAVAIN_ROUTING_POLICY'];digest=hashlib.sha256(pathlib.Path(policy).read_bytes()).hexdigest()
route=json.loads(subprocess.check_output(ic+['--json','route','dispatch','--policy='+policy,'--role='+role,'--context-file='+os.environ['CLAVAIN_DECISION_CONTEXT']]+(['--producer-identity='+producer] if producer else [])))
model=route['profile']['model'];uncapped=os.environ['PREPARE_FIXTURE_MODE']=='uncapped'
assert int(os.environ['CLAVAIN_TOKEN_BUDGET']) == (0 if uncapped else (1000 if role=='planning' else 975))
if role=='planning':out.write_text(json.dumps({'plan':'Fixture plan preserving the exact accepted ruling.','specification':None}))
else:out.write_text('Fixture independent review.\nVERDICT: PASS\n')
with open(os.environ['CLAVAIN_REVIEW_EVENTS'],'a') as f:f.write(json.dumps({'type':'turn.completed','usage':{'input_tokens':2000 if uncapped else 20,'output_tokens':5}})+'\n')
context={'terminal':True,'role':role,'producer_identity':producer,'execution':{'model':model},'result':{'exit_code':0,'failure_class':'success'},'resolved_route':{'frontier_required':True,'policy_hash':digest},'fixture':True}
subprocess.check_call(ic+['route','record','--agent='+role,'--role='+role,'--model='+model,'--rule=fixture','--project='+arg('-C'),'--dispatch='+os.environ['CLAVAIN_DISPATCH_ID'],'--run='+os.environ['CLAVAIN_RUN_ID'],'--policy-hash='+digest,'--context='+json.dumps(context)],stdout=subprocess.DEVNULL)
out.with_suffix(out.suffix+'.verdict').write_text('--- VERDICT ---\nSTATUS: pass\nSUMMARY: fixture\n---\n')
`), 0600)
	t.Setenv("CLAVAIN_DIR", fake)
	t.Setenv("CLAVAIN_ROUTING_POLICY", policy)
	if _, err := ratifyPrepare(base, s, reviewRun); err != nil {
		t.Fatal(err)
	}
	_, path, err := submitPrepare(base, s)
	if err != nil {
		t.Fatal(err)
	}
	if err = workPrepare(path); err != nil {
		t.Log("receipt", path)
		data, _ := os.ReadFile(path)
		t.Log(string(data))
		for _, role := range []string{"planning", "plan-review"} {
			data, _ = os.ReadFile(filepath.Join(filepath.Dir(path), "attempt-1", role, "worker.log"))
			t.Log(role, string(data))
		}
		t.Fatal(err)
	}
	r, _, err := readPrepare(base, s)
	if err != nil {
		t.Fatal(err)
	}
	wantUsage := 50
	if mode == "uncapped" {
		wantUsage = 4010
	}
	if r.Status != "reviewed" || len(r.Attempts) != 1 || prepareUsage(r) != wantUsage || r.BundleDigest == "" {
		t.Fatalf("bad preparation receipt: %+v", r)
	}
	if r.KernelDB == "" {
		t.Fatal("missing pinned kernel")
	}
	// A new nearer database must not capture resumed accounting.
	if _, err := reviewRun(s.Project, "ic", "--db="+filepath.Join(s.Project, ".clavain", "intercore.db"), "init"); err != nil {
		t.Fatal(err)
	}
	for _, phase := range []preparePhase{r.Attempts[0].Planner, r.Attempts[0].Reviewer} {
		if phase.Overshoot != 0 || !phase.UsageComplete {
			t.Fatal("incorrect terminal accounting", phase)
		}
		data, err := prepareRunner(r)(s.Project, "ic", "--json", "dispatch", "status", phase.DispatchID)
		var dispatch struct {
			Run      string `json:"scope_id"`
			TokensIn int    `json:"in_tokens"`
		}
		if err != nil || json.Unmarshal(data, &dispatch) != nil || dispatch.Run != r.RunID {
			t.Fatal("dispatch is not bound to its run", err, string(data))
		}
		if dispatch.TokensIn != wantUsage/2 {
			t.Fatal("kernel lost phase usage", string(data))
		}
	}
	before, _ := os.ReadFile(path)
	if err = workPrepare(path); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("reviewed restart mutated receipt")
	}
	data, err := prepareRunner(r)(s.Project, "ic", "--json", "run", "budget", r.RunID)
	if err != nil {
		t.Fatal(err)
	}
	var budget struct {
		Used int `json:"used"`
	}
	json.Unmarshal(data, &budget)
	if mode == "capped" && budget.Used != wantUsage {
		t.Fatal("phase usage did not reconcile", string(data))
	}
	if mode == "uncapped" {
		var b map[string]any
		if json.Unmarshal(data, &b) != nil || b["budget"] != nil || b["message"] != "no budget set" {
			t.Fatal("uncapped kernel has token budget", string(data))
		}
	}
	// Simulate a crash after reviewer completion but before the reviewed save.
	// reviewWrite indents embedded route JSON; this must not alter its digest.
	expected := r.BundleDigest
	r.Status, r.BundleDigest = "reviewing", ""
	if err = reviewWrite(path, r); err != nil {
		t.Fatal(err)
	}
	if err = workPrepare(path); err != nil {
		t.Fatal(err)
	}
	recovered, _, err := readPrepare(base, s)
	if err != nil || recovered.BundleDigest != expected || prepareUsage(recovered) != wantUsage {
		t.Fatal("review-complete restart changed bundle or spend", err, recovered.BundleDigest, expected)
	}
	t.Log("fixture preparation", r.RunID, r.Attempts[0].Planner.DispatchID, r.Attempts[0].Reviewer.DispatchID)
}
