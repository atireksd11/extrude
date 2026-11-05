"""A local env file fills missing variables and leaves the process alone otherwise."""

import os

from extrude.harness.envfile import load_env


def test_a_local_file_fills_only_missing_variables(tmp_path, monkeypatch):
    monkeypatch.delenv("EXTRUDE_MODEL", raising=False)
    monkeypatch.delenv("EXTRUDE_MODEL_URL", raising=False)
    monkeypatch.setenv("EXTRUDE_MODEL_KEY", "already-set")
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(
            [
                "# comment",
                'export EXTRUDE_MODEL="openai/gpt-6-luna"',
                "EXTRUDE_MODEL_KEY=from-file",
                "EXTRUDE_MODEL_URL=",
                "not a pair",
            ]
        ),
        encoding="utf-8",
    )
    load_env(path)
    assert os.environ["EXTRUDE_MODEL"] == "openai/gpt-6-luna"
    assert os.environ["EXTRUDE_MODEL_KEY"] == "already-set"
    assert "EXTRUDE_MODEL_URL" not in os.environ
