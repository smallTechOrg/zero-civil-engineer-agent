"""Settings — defaults, env overrides, Gemini key detection. No LLM key required.

(LLM client provider-construction behaviour is covered by the graph slice's tests.)
"""


def _fresh_settings(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import config.settings as m

    m._settings = None
    return m.get_settings()


def test_project_defaults(monkeypatch):
    for var in (
        "AGENT_LLM_MODEL",
        "AGENT_ARTIFACTS_DIR",
        "AGENT_PORT",
        "AGENT_GEMINI_INPUT_COST_PER_MTOK",
        "AGENT_GEMINI_OUTPUT_COST_PER_MTOK",
    ):
        monkeypatch.delenv(var, raising=False)
    from config.settings import Settings

    s = Settings(_env_file=None)  # pure code defaults — ignore the developer's .env
    assert s.llm_model == "gemini-2.5-pro"
    assert s.artifacts_dir == "data/artifacts"
    assert s.port == 8001
    assert s.gemini_input_cost_per_mtok == 1.25
    assert s.gemini_output_cost_per_mtok == 10.0
    assert s.database_url == "sqlite:///./data/agent.db"


def test_artifacts_dir_env_override(monkeypatch, tmp_path):
    s = _fresh_settings(monkeypatch, tmp_path, AGENT_ARTIFACTS_DIR="/tmp/somewhere/else")
    assert s.artifacts_dir == "/tmp/somewhere/else"


def test_port_env_override(monkeypatch, tmp_path):
    s = _fresh_settings(monkeypatch, tmp_path, AGENT_PORT="8003")
    assert s.port == 8003


def test_cost_rates_env_override(monkeypatch, tmp_path):
    s = _fresh_settings(
        monkeypatch,
        tmp_path,
        AGENT_GEMINI_INPUT_COST_PER_MTOK="2.5",
        AGENT_GEMINI_OUTPUT_COST_PER_MTOK="15.0",
    )
    assert s.gemini_input_cost_per_mtok == 2.5
    assert s.gemini_output_cost_per_mtok == 15.0


def test_gemini_key_detected_from_env(monkeypatch, tmp_path):
    s = _fresh_settings(
        monkeypatch,
        tmp_path,
        AGENT_GEMINI_API_KEY="AIza-fake",
    )
    assert s.gemini_api_key == "AIza-fake"


def test_llm_model_env_override(monkeypatch, tmp_path):
    s = _fresh_settings(
        monkeypatch,
        tmp_path,
        AGENT_LLM_MODEL="gemini-2.5-flash",
    )
    assert s.llm_model == "gemini-2.5-flash"
