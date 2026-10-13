#!/usr/bin/env bats
# Sylveste-7t3n — the goal-shape guide exists and both goal commands point at it.
#
# A cheap guard against the failure this whole change is about. The shape spec
# only helps if it lives in ONE place and the commands that draft goals actually
# reference it; a renamed file or a dropped reference silently returns us to
# re-improvising the form per draft, which is how five consecutive /goal blocks
# went out with rulings written in the user's voice.

setup() {
    ROOT="$BATS_TEST_DIRNAME/../.."
    GUIDE="$ROOT/docs/guide-goal-shape.md"
}

@test "the goal-shape guide exists" {
    [ -f "$GUIDE" ]
}

@test "goal-form references the guide" {
    grep -q "guide-goal-shape.md" "$ROOT/commands/goal-form.md"
}

@test "next-goal references the guide" {
    grep -q "guide-goal-shape.md" "$ROOT/commands/next-goal.md"
}

@test "the guide carries the seven rules and the section template" {
    for section in OUTCOME "WHO'S WAITING" PREMISE "GATE n" "DONE WHEN" OUT; do
        grep -q "$section" "$GUIDE"
    done
    # Named so a reader can match a lint finding to the rule it came from.
    for rule in ventriloquism "plan detail" "pre-ruled call" "self-graded" "no bar"; do
        grep -qi "$rule" "$GUIDE"
    done
}

@test "the guide names the lint that enforces it" {
    grep -q "ic goal lint-condition" "$GUIDE"
}

# mk-3mo0w — the premise test and the deepen pass reach the commands that draft.
@test "goal-form requires PREMISE at C3+ and offers deepen" {
    grep -q "C3+: the condition carries \`PREMISE\`" "$ROOT/commands/goal-form.md"
    grep -q "The executor runs that test first" "$ROOT/commands/goal-form.md"
    grep -q "disproven premise escalates immediately" "$ROOT/commands/goal-form.md"
    grep -q "/clavain:deepen" "$ROOT/commands/goal-form.md"
}

@test "brainstorm offers deepen in Phase 2 at numeric C3+" {
    phase2=$(awk '/^### Phase 2:/{p=1;next} /^### /{p=0} p' "$ROOT/commands/brainstorm.md")
    grep -q "/clavain:deepen" <<<"$phase2"
    grep -q "complexity\` is 3 or higher" <<<"$phase2"
    ! grep -q "complexity is \`complex\`" "$ROOT/commands/brainstorm.md"
}
