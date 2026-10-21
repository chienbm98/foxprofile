import subprocess
import sys
import textwrap


def test_env_in_working_directory_is_loaded(tmp_path):
    (tmp_path / ".env").write_text("FOXPROFILE_MACHINE_NAME=from-cwd\n")
    code = textwrap.dedent(
        """
        import sys; sys.path.insert(0, sys.argv[1])
        from src.core import config
        print(config.MACHINE_NAME)
        """
    )
    repo = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    out = subprocess.run(
        [sys.executable, "-c", code, repo],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={k: v for k, v in __import__("os").environ.items() if k != "FOXPROFILE_MACHINE_NAME"},
    )
    assert out.stdout.strip() == "from-cwd", out.stderr
