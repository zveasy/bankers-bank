# Audit Backup & Restore Runbook

## Purpose
Ensure at-least-once export of `credit_audit_journal` rows and provide a deterministic, idempotent restore path.

## Export Path
* CronJob: `k8s/cronjob-audit-exporter.yaml` (5-min interval).
* Uses `bin/audit-export` inside service image.
* Environment:
  * `DATABASE_URL` – Postgres DSN.
  * `AUDIT_EXPORT_DIR` – persistent volume for `.ndjson.gz` exports.
* Metrics exposed by `AuditExporter`:
  * `audit_export_rows_selected_total`
  * `audit_export_files_written_total{result}`
  * `audit_export_duration_seconds`
  * `audit_backlog_rows`

## Restore Path
* Script: `scripts/restore_audit_from_ndjson.py`.
* Safe, idempotent: skips rows whose `id` already exists.
* Example:

```bash
python scripts/restore_audit_from_ndjson.py \
  --db-url "$DATABASE_URL" exports/*.ndjson.gz
```

## Failure Modes & Troubleshooting
| Symptom | Action |
|---|---|
| CronJob pod CrashLoop | `kubectl logs` & check DB connectivity, volume permissions. |
| Backlog gauge growing | Increase batch size (`AUDIT_EXPORT_BATCH`) or CronJob frequency. |
| Restore script slow | Run from a node close to DB and ensure `work_mem` is adequate. |

## SLA / RPO
* RPO < 10 min (5-min schedule + 5-min lag cutoff).
* RTO determined by volume of data & restore hardware (~2M rows/min typical).
