import sqlite3, os
conn = sqlite3.connect('data/orca_state.db')

print('=== Current Clusters ===')
rows = conn.execute("""
    SELECT context_cluster_id, COUNT(1) AS snapshots
    FROM lesson_context_snapshot
    WHERE source_event_type='backtest_backfill'
    GROUP BY context_cluster_id
    ORDER BY context_cluster_id
""").fetchall()
for r in rows:
    print(r)

print('')
print('=== Total cluster snapshots ===')
result = conn.execute("""
    SELECT COUNT(DISTINCT context_cluster_id) FROM lesson_context_snapshot 
    WHERE context_cluster_id IS NOT NULL
""").fetchone()[0]
print('unique clusters:', result)

result = conn.execute("""
    SELECT COUNT(1) FROM lesson_context_snapshot
    WHERE context_cluster_id IS NULL
""").fetchone()[0]
print('snapshots without cluster:', result)

print('')
print('=== Backfill snapshot date range ===')
result = conn.execute("""
    SELECT MIN(trading_date), MAX(trading_date)
    FROM lesson_context_snapshot
    WHERE source_event_type='backtest_backfill'
""").fetchone()
print('range:', result)

print('')
print('=== snapshot_cluster_mapping ===')
try:
    result = conn.execute("SELECT COUNT(1) FROM snapshot_cluster_mapping").fetchone()[0]
    print('mapping rows:', result)
except Exception as e:
    print('table not exist or error:', e)

conn.close()
