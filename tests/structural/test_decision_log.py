"""decision-log.sh: header, single-line cells, formula-prefix quoting."""
import subprocess


def run(project_root, log, *cells):
    return subprocess.run(
        ["bash", str(project_root / "scripts" / "decision-log.sh"), str(log), *cells],
        capture_output=True, text=True, timeout=30,
    )


def test_writes_header_once_and_one_row_per_call(project_root, tmp_path):
    log = tmp_path / "d.tsv"
    assert run(project_root, log, "p", "d1", "w", "e", "r").returncode == 0
    assert run(project_root, log, "p", "d2", "w", "e", "r").returncode == 0
    lines = log.read_text().splitlines()
    assert lines[0] == "ts\tphase\tdecision\twhy\tevidence\tresult"
    assert len(lines) == 3
    assert all(len(line.split("\t")) == 6 for line in lines)


def test_cells_stay_single_line_and_formula_prefixes_are_quoted(project_root, tmp_path):
    log = tmp_path / "d.tsv"
    assert run(project_root, log, "p", "a\tb\nc", "=SUM(A1)", "+1", "@x").returncode == 0
    row = log.read_text().splitlines()[1].split("\t")
    assert len(row) == 6
    assert row[2] == "a b c"
    assert row[3:] == ["'=SUM(A1)", "'+1", "'@x"]


def test_wrong_argument_count_is_a_usage_error(project_root, tmp_path):
    result = run(project_root, tmp_path / "d.tsv", "only", "three")
    assert result.returncode == 2
    assert not (tmp_path / "d.tsv").exists()
