"""Turn an n8n export into the versioned workflow files, and refuse secrets.

    python automation/n8n/normalize_workflows.py <export folder> automation/n8n/workflows

An export carries what belongs to one n8n instance: dates, version IDs, the
project and owner it is shared with (the owner's email included) and the IDs
of the credentials there. Those are dropped, so the files only change when a
workflow does, and credentials are referred to by name: n8n links each one to
the credential of the same name and type when the files are imported.

The files are then checked for anything that looks like a secret or a
personal address, and nothing is written if one is found.
"""

import json
import re
import sys
from pathlib import Path

# Workflow ID in n8n -> file name in the repository.
FILES = {
    "quetzalDigest001": "daily-digest.json",
    "quetzalFailure01": "pipeline-failure.json",
    "quetzalNotifyErr": "notification-error.json",
}
KEPT = ("id", "name", "active", "nodes", "connections", "settings", "pinData", "tags")
# Placeholder IDs that exist in no instance, so import falls back to the name.
CREDENTIAL_IDS = {
    "httpHeaderAuth": "quetzalWebhookCr",
    "telegramApi": "quetzalTelegramC",
    "smtp": "quetzalSmtpCrede",
}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.test")
SECRET_KEYS = re.compile(r"(password|passwd|secret|token|apikey|api_key|accesstoken|authorization)", re.IGNORECASE)
TELEGRAM_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b")


def normalize(workflow: dict) -> dict:
    if workflow.get("pinData"):
        # Pinned data is a copy of real input, such as a whole digest.
        raise ValueError(f"{workflow['name']}: unpin the data of every node before exporting")
    kept = {key: workflow[key] for key in KEPT if key in workflow}
    for node in kept["nodes"]:
        for credential_type, reference in node.get("credentials", {}).items():
            if credential_type not in CREDENTIAL_IDS:
                raise ValueError(f"{workflow['name']}: unexpected credential type {credential_type}")
            reference["id"] = CREDENTIAL_IDS[credential_type]
    return kept


def problems(value, path: str = "") -> list[str]:
    """Places that look like a secret or a personal email address."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and SECRET_KEYS.search(key) and item and not item.startswith("="):
                found.append(f"{path}.{key}: a literal value under a secret-like name")
            found += problems(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += problems(item, f"{path}[{index}]")
    elif isinstance(value, str):
        for match in EMAIL.finditer(value):
            if not match.group().lower().endswith(ALLOWED_EMAIL_DOMAINS):
                found.append(f"{path}: email address {match.group()}")
        if TELEGRAM_TOKEN.search(value):
            found.append(f"{path}: something shaped like a Telegram bot token")
        if "Bearer " in value:
            found.append(f"{path}: a bearer token")
    return found


def main(export_dir: Path, workflows_dir: Path) -> None:
    exported = {}
    for path in sorted(export_dir.glob("*.json")):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        if workflow["id"] not in FILES:
            sys.exit(f"{path.name}: workflow {workflow['id']} ({workflow['name']}) is not one of this project's")
        exported[workflow["id"]] = normalize(workflow)
    missing = set(FILES) - set(exported)
    if missing:
        sys.exit(f"missing from the export: {', '.join(sorted(missing))}")

    found = [f"{FILES[i]}{p}" for i, workflow in exported.items() for p in problems(workflow)]
    if found:
        sys.exit("nothing written; review these first:\n" + "\n".join(found))

    workflows_dir.mkdir(parents=True, exist_ok=True)
    for workflow_id, workflow in exported.items():
        target = workflows_dir / FILES[workflow_id]
        target.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {target}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
