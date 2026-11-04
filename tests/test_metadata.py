from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_blueprints_and_services_parse():
    class BlueprintLoader(yaml.SafeLoader):
        pass

    BlueprintLoader.add_constructor(
        "!input", lambda loader, node: loader.construct_scalar(node)
    )
    for path in (ROOT / "blueprints").rglob("*.yaml"):
        data = yaml.load(path.read_text(), Loader=BlueprintLoader)
        assert data["blueprint"]["domain"] == "automation"
        assert data["actions"] and data["triggers"]
    services = yaml.safe_load(
        (ROOT / "custom_components/glance_clock/services.yaml").read_text()
    )
    for name in (
        "show_calendar",
        "announce_calendar",
        "announce",
    ):
        assert "entry_id" in services[name]["fields"]
