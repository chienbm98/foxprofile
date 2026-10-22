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


def test_camoufox_home_redirects_the_browser_cache(tmp_path):
    import os
    import pathlib
    import subprocess
    import sys

    repo = str(pathlib.Path(__file__).resolve().parents[1])
    code = "import src, camoufox.pkgman as p; print(p.INSTALL_DIR)"
    home = tmp_path / "browser-cache"
    env = {**os.environ, "FOXPROFILE_CAMOUFOX_HOME": str(home), "PYTHONPATH": repo}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=tmp_path
    )
    assert out.stdout.strip() == str(home), out.stderr
    env.pop("FOXPROFILE_CAMOUFOX_HOME")
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=tmp_path
    )
    assert out.stdout.strip() != str(home) and "camoufox" in out.stdout.lower()
