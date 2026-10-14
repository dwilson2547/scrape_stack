---
title: Rebuilds drift: unpinned deps caused webcache outage
date: 2026-10-13
tags: incident,scrape-stack,docker
source: web-scrapers/scrape-stack/docs/issues/2026_10_13_webcache_sqlalchemy_2_1_psycopg_default_crash.md
---

The scrape-stack service images build from unpinned requirements (e.g. sqlalchemy>=2.0.0), so any rebuild can silently pick up a new major/minor and break a live service: webcache crash-looped when a rebuild resolved SQLAlchemy 2.1.4, whose postgresql:// default dialect changed from psycopg2 to psycopg3. Pin upper bounds or use a lockfile before the next rebuild of any cache service. See: docs/issues/2026_10_13_webcache_sqlalchemy_2_1_psycopg_default_crash.md
