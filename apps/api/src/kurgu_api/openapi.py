"""OpenAPI şemasını dosyaya yazar: `uv run kurgu-openapi packages/api-client/openapi.json`."""

import json
import sys
from pathlib import Path

from kurgu_api.main import create_app


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
