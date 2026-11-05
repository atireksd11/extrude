"""Local copilot commands. Audit does not call a model."""

import argparse
import json
import sys
from pathlib import Path

from extrude.copilot.api import CopilotRequest, handle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="extrude.copilot")
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate")
    generate.add_argument("text")
    generate.add_argument("--offline", action="store_true")
    generate.add_argument("--filament", default="PLA")

    audit = sub.add_parser("audit")
    audit.add_argument("path")
    audit.add_argument("--filament", default="PLA")
    audit.add_argument("--repair", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "generate":
        body = CopilotRequest(text=args.text, offline=args.offline, filament=args.filament)
    else:
        file = Path(args.path)
        if not file.is_file():
            print(json.dumps({"status": "stopped", "detail": f"file not found: {file}"}))
            return 1
        body = CopilotRequest(
            artifact=file.read_text(encoding="utf-8"),
            filename=file.name,
            filament=args.filament,
            repair=args.repair,
        )
    result = handle(body)
    print(json.dumps(result.model_dump(), indent=2))
    return 0 if result.status == "checked" else 1


if __name__ == "__main__":
    sys.exit(main())
