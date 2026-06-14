#!/usr/bin/env python3
"""vidcache — content-addressed video cache service.

Usage::

    python main.py [--config config.yaml]
"""
from __future__ import annotations

import argparse
import sys

import uvicorn

from app.api import create_app
from app.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="vidcache — content-addressed video cache service"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        metavar="FILE",
        help="Path to YAML configuration file (default: config.yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to load config: {exc}", file=sys.stderr)
        sys.exit(1)

    app = create_app(config)
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
