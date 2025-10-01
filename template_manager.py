import json
import os
from typing import Dict, Any, List, Optional

APP_DIR = os.path.join(os.path.expanduser("~"), ".photo_watermark")
TEMPLATE_DIR = os.path.join(APP_DIR, "templates")
LAST_SETTINGS_PATH = os.path.join(APP_DIR, "last_settings.json") 


def ensure_dirs():
    os.makedirs(TEMPLATE_DIR, exist_ok=True)


def save_template(name: str, settings: Dict[str, Any]) -> str:
    ensure_dirs()
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-", "."))
    path = os.path.join(TEMPLATE_DIR, f"{safe_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return path


def list_templates() -> List[str]:
    ensure_dirs()
    files = []
    for fn in os.listdir(TEMPLATE_DIR):
        if fn.lower().endswith(".json"):
            files.append(os.path.splitext(fn)[0])
    return sorted(files)


def load_template(name: str) -> Optional[Dict[str, Any]]:
    ensure_dirs()
    path = os.path.join(TEMPLATE_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_template(name: str) -> bool:
    ensure_dirs()
    path = os.path.join(TEMPLATE_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def save_last_settings(settings: Dict[str, Any]) -> None:
    ensure_dirs()
    with open(LAST_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_last_settings() -> Optional[Dict[str, Any]]:
    ensure_dirs()
    if os.path.exists(LAST_SETTINGS_PATH):
        with open(LAST_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None