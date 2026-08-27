"""Generate the checked-in OpenAPI 3.1 contract from the FastAPI application."""

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.main import app


target = Path(__file__).resolve().parents[1] / "packages" / "contracts" / "openapi.yaml"
target.write_text(
    yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True),
    encoding="utf-8",
)
