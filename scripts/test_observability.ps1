# Produce a test snapshot message
Invoke-RestMethod https://127.0.0.1:9000/snapshot -Method POST

# Check counters changed
(Invoke-WebRequest https://127.0.0.1:8001/).Content -split "`n" |
  Where-Object { $_ -match 'asset_snapshots_(consumed|db_inserts)_total|asset_snapshot_process_latency' }
