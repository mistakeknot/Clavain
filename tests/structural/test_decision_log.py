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


def test_quoted_formula_cells_and_concurrent_writers(project_root, tmp_path):
    import csv
    from concurrent.futures import ThreadPoolExecutor

    log = tmp_path / "d.tsv"
    assert run(project_root, log, "p", '"=1+1"', "w", "e", "r").returncode == 0
    with open(log, newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    assert rows[1][2].startswith("'")

    log2 = tmp_path / "c.tsv"
    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(lambda i: run(project_root, log2, "p", f"d{i}", "w", "e", "r").returncode, range(60)))
    assert set(codes) == {0}
    lines = log2.read_text().splitlines()
    assert len(lines) == 61
    assert lines.count("ts\tphase\tdecision\twhy\tevidence\tresult") == 1
    assert sorted(line.split("\t")[2] for line in lines[1:]) == sorted(f"d{i}" for i in range(60))
    assert all(len(line.split("\t")) == 6 for line in lines)


def test_mkdir_lock_fallback_without_flock(project_root, tmp_path):
    import os
    import shutil
    from concurrent.futures import ThreadPoolExecutor

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "date", "sleep", "mkdir", "rmdir"):
        os.symlink(shutil.which(tool), bin_dir / tool)
    log = tmp_path / "f.tsv"

    def call(i):
        return subprocess.run(
            [str(bin_dir / "bash"), str(project_root / "scripts" / "decision-log.sh"),
             str(log), "p", f"d{i}", "w", "e", "r"],
            capture_output=True, text=True, timeout=60, env={"PATH": str(bin_dir)},
        ).returncode

    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(call, range(30)))
    assert set(codes) == {0}
    lines = log.read_text().splitlines()
    assert len(lines) == 31
    assert lines.count("ts\tphase\tdecision\twhy\tevidence\tresult") == 1
    assert sorted(line.split("\t")[2] for line in lines[1:]) == sorted(f"d{i}" for i in range(30))
    assert all(len(line.split("\t")) == 6 for line in lines)
    assert not (tmp_path / "f.tsv.lock.d").exists()


def _start(project_root, log, env=None, bash="bash"):
    return subprocess.Popen(
        [bash, str(project_root / "scripts" / "decision-log.sh"), str(log), "p", "d", "w", "e", "r"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )


def test_writer_waits_while_flock_is_held(project_root, tmp_path):
    import fcntl
    import shutil
    import time

    if shutil.which("flock") is None:
        import pytest
        pytest.skip("flock not installed")
    log = tmp_path / "h.tsv"
    log.touch()
    with open(log, "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        proc = _start(project_root, log)
        time.sleep(1)
        assert proc.poll() is None
        assert log.read_text() == ""
        fcntl.flock(held, fcntl.LOCK_UN)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, err
    assert len(log.read_text().splitlines()) == 2


def test_writer_waits_while_mkdir_lock_is_held(project_root, tmp_path):
    import os
    import shutil
    import time

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "date", "sleep", "mkdir", "rmdir"):
        os.symlink(shutil.which(tool), bin_dir / tool)
    log = tmp_path / "m.tsv"
    lock = tmp_path / "m.tsv.lock.d"
    lock.mkdir()
    proc = _start(project_root, log, env={"PATH": str(bin_dir)}, bash=str(bin_dir / "bash"))
    time.sleep(1)
    assert proc.poll() is None
    assert not log.exists()
    lock.rmdir()
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, err
    assert len(log.read_text().splitlines()) == 2
    assert not lock.exists()
