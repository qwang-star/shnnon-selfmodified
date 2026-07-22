from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "models.yaml"


def load_models_config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_all_tiers_prefer_openai_gpt_55():
    config = load_models_config()

    for tier in ("small", "medium", "large"):
        first = config["model_tiers"][tier]["providers"][0]
        assert first["provider"] == "openai"
        assert first["model"] == "gpt-5.5"


def test_gpt_55_exists_in_openai_catalog():
    config = load_models_config()
    model = config["model_catalog"]["openai"]["gpt-5.5"]

    assert model["model_id"] == "gpt-5.5"
    assert model["supports_streaming"] is True
