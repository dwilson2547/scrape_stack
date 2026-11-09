#!/usr/bin/env python3
"""vidcache — Local-to-S3 migration helper.

For each video row in the SQLite index this script:
  1. Locates the file in local storage.
  2. Uploads it to the configured S3 backend.
  3. Verifies the uploaded size matches.

Use --dry-run to inspect what would be migrated without making any changes.

Usage::

    python migrate_to_s3.py --config config.yaml [--dry-run]

After a successful migration, update config.yaml to set::

    video_store:
      backend: s3

and restart the service.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import yaml


def _load_raw(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def migrate(config_path: str, dry_run: bool) -> None:
    raw = _load_raw(config_path)

    local_cfg = raw.get("video_store", {}).get("local")
    if not local_cfg:
        print("error: video_store.local.root is not set in config", file=sys.stderr)
        sys.exit(1)
    local_root = Path(local_cfg["root"])

    s3_cfg = raw.get("video_store", {}).get("s3")
    if not s3_cfg and not dry_run:
        print("error: video_store.s3 config is required for migration", file=sys.stderr)
        sys.exit(1)

    db_path = raw.get("index", {}).get("db_path", "/data/vidcache/index.db")
    dedup = raw.get("dedup", {})
    multipart_threshold_mb = dedup.get("multipart_threshold_mb", 100)
    multipart_part_size_mb = dedup.get("multipart_part_size_mb", 64)

    # Fetch all video rows up-front so we can report totals
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT hash, bucket, prefix, size_bytes FROM videos"
    ).fetchall()
    conn.close()

    total = len(rows)
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Migrating {total} video(s) from {local_root} to S3…")

    store = None
    if not dry_run:
        from app.storage.s3 import S3VideoStore  # noqa: PLC0415 — conditional import

        store = S3VideoStore(
            endpoint=s3_cfg["endpoint"],
            access_key=s3_cfg["access_key"],
            secret_key=s3_cfg["secret_key"],
            region=s3_cfg.get("region", "us-east-1"),
            multipart_threshold_mb=multipart_threshold_mb,
            multipart_part_size_mb=multipart_part_size_mb,
        )

    ok = skipped = failed = 0

    for i, row in enumerate(rows, 1):
        h = row["hash"]
        bucket: str = row["bucket"]
        p: str = row["prefix"] or ""
        size: int | None = row["size_bytes"]

        # Reconstruct local path using the same sharding scheme
        shard = Path(h[:2]) / h[2:4] / f"{h}.mp4"
        local_path = local_root / bucket / p / shard if p else local_root / bucket / shard

        label = f"[{i}/{total}] {h[:16]}…"

        if not local_path.exists():
            print(f"{label} MISSING ({local_path}) — skip")
            failed += 1
            continue

        if dry_run:
            size_desc = f"{size:,} bytes" if size else "unknown size"
            print(f"{label} would upload ({size_desc})")
            ok += 1
            continue

        try:
            if store.exists(bucket, p, h):
                print(f"{label} already in S3 — skip")
                skipped += 1
                continue

            with open(local_path, "rb") as f:
                store.put(bucket, p, h, f, size)

            # Verify
            s3_size = store.get_size(bucket, p, h)
            if size and s3_size != size:
                print(f"{label} WARNING size mismatch (local={size} s3={s3_size})")
            else:
                print(f"{label} OK")
            ok += 1

        except Exception as exc:  # noqa: BLE001
            print(f"{label} FAILED: {exc}")
            failed += 1

    print(f"\nDone. {ok} migrated, {skipped} skipped, {failed} failed.")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate vidcache from local filesystem storage to S3"
    )
    parser.add_argument(
        "--config", "-c", default="config.yaml", metavar="FILE",
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be migrated without uploading anything",
    )
    args = parser.parse_args()
    migrate(args.config, args.dry_run)


if __name__ == "__main__":
    main()
