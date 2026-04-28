import sqlite3
conn = sqlite3.connect('data/orca_state.db')

print('=== Backfill snapshots near end ===')
rows = conn.execute("""
    SELECT trading_date, snapshot_id, vix_level
    FROM lesson_context_snapshot
    WHERE source_event_type='backtest_backfill'
      AND trading_date >= '2026-04-10'
    ORDER BY trading_date
""").fetchall()
for r in rows:
    print(r)

print('')
print('=== Backtest snapshots near end ===')
rows = conn.execute("""
    SELECT trading_date, snapshot_id, vix_level
    FROM lesson_context_snapshot
    WHERE source_event_type='backtest'
      AND trading_date >= '2026-04-10'
    ORDER BY trading_date
""").fetchall()
for r in rows:
    print(r)

conn.close()
