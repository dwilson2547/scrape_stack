# PostgreSQL on Kubernetes with TrueNAS NFS Storage: Permission Errors

## Problem

When running the official `postgres` Docker image on Kubernetes with an NFS-backed PVC (TrueNAS), the container fails on startup with errors like:

```
chown: changing ownership of '/var/lib/postgresql/data': Operation not permitted
```

or silently corrupts the directory permissions, making it unreadable without root.

## Root Cause

The official postgres image entrypoint (`docker-entrypoint.sh`) runs as root and unconditionally executes:

```bash
chown -R postgres "$PGDATA" "$PGDATA/.."
chmod 700 "$PGDATA"
```

This causes two separate problems on NFS:

1. **With NFS all-squash enabled** (TrueNAS default): all operations including root are mapped to `nobody:nobody`, so `chown` fails with "Operation not permitted".

2. **With all-squash disabled and no_root_squash** (root passes through to NFS server): `chown` succeeds, but `chmod` on a ZFS dataset using NFSv4 ACLs strips the inherited ACL entries from the directory, leaving it as `drwx------` with no `+` flag. The postgres process then can't access its own data directory after dropping privileges.

Setting `PGDATA` to a subdirectory (e.g. `/var/lib/postgresql/data/pgdata`) does not help because the entrypoint also chowns and chmods `$PGDATA/..`, which is the mount point.

## Fix

Run the container as uid 999 (the `postgres` user in the official image) via `securityContext`:

```yaml
containers:
  - name: postgres
    image: postgres:16
    securityContext:
      runAsUser: 999
      runAsGroup: 999
```

The entrypoint branches on `id -u`:

```bash
if [ "$(id -u)" = '0' ]; then
    # chown/chmod happens here — skipped when not root
fi
```

When the container starts as uid 999, the entire chown/chmod block is skipped. The NFS directory retains its inherited NFSv4 ACLs (`drwxrwxrwx+`) and postgres initializes normally.

## TrueNAS NFS Configuration

For this to work, the NFS export must have:

- **all-squash disabled** — so uid 999 from the Kubernetes node passes through to the NFS server as-is
- **no_root_squash** is not required since the container no longer runs as root
- **NFSv4 ACL inheritance enabled** on the dataset — ensure all ACEs have "File Inherit" and "Directory Inherit" flags set, so newly provisioned PVC directories get the correct permissions automatically

## Storage Class

The PVC must explicitly reference the NFS storage class:

```yaml
volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      storageClassName: nfs-dataset
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 100Gi
```
