import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_env_not_tracked():
    files = tracked()
    assert ".env" not in files
    assert ".env" in (ROOT / ".gitignore").read_text().split()


def test_env_example_has_no_values():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            assert value.strip() == "", f"{key} should be empty in .env.example"


def test_no_live_key_in_tracked_files():
    env = ROOT / ".env"
    if not env.exists():
        return
    secrets = [l.partition("=")[2].strip() for l in env.read_text().splitlines() if "=" in l]
    secrets = [s for s in secrets if len(s) > 8]
    for f in tracked():
        p = ROOT / f
        if p.is_file():
            text = p.read_text(errors="ignore")
            assert not any(s in text for s in secrets), f"secret found in {f}"
