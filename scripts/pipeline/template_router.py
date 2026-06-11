from pathlib import Path

from .config_loader import load_yaml


def route_template(registry_path: Path, template_path: Path, user_request: str = "") -> dict:
    registry = load_yaml(registry_path)
    name = template_path.name
    templates = registry["templates"]
    if name not in templates:
        matches = [key for key in templates if key in user_request]
        if not matches:
            raise KeyError(f"template not registered: {name}")
        name = matches[0]
    route = dict(templates[name])
    route["template_name"] = name
    return route
