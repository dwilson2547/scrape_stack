import argparse
import sys

import uvicorn

from app.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="filecache service")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config file")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Failed to load config from {args.config!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    from app.api import create_app
    app = create_app(config)

    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
