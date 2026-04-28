import sqlite3
conn = sqlite3.connect('data/orca_state.db')

print('=== Backtest dates ===')
result = conn.execute("""
    SELECT MIN(trading_date), MAX(trading_date), COUNT(DISTINCT trading_date)
    FROM lesson_context_snapshot
    WHERE source_event_type='backtest'
""").fetchone()
print(result)

print('')
print('=== Backfill dates ===')
result = conn.execute("""
    SELECT MIN(trading_date), MAX(trading_date), COUNT(DISTINCT trading_date)
    FROM lesson_context_snapshot
    WHERE source_event_type='backtest_backfill'
""").fetchone()
print(result)

print('')
print('=== Backtest dates NOT in backfill (mismatch) ===')
result = conn.execute("""
    SELECT trading_date FROM lesson_context_snapshot
    WHERE source_event_type='backtest'
      AND trading_date NOT IN (
        SELECT trading_date FROM lesson_context_snapshot
        WHERE source_event_type='backtest_backfill'
      )
    ORDER BY trading_date
""").fetchall()
print('mismatch count:', len(result))
for r in result[:10]:
    print(' ', r[0])

print('')
print('=== Backfill dates NOT in backtest (overlap missing) ===')
result = conn.execute("""
    SELECT COUNT(DISTINCT trading_date) FROM lesson_context_snapshot
    WHERE source_event_type='backtest_backfill'
      AND trading_date NOT IN (
        SELECT trading_date FROM lesson_context_snapshot
        WHERE source_event_type='backtest'
      )
""").fetchone()[0]
print('backfill-only dates (2-year history):', result)

print('')
print('=== Common dates ===')
result = conn.execute("""
    SELECT COUNT(DISTINCT bt.trading_date)
    FROM lesson_context_snapshot bt
    INNER JOIN lesson_context_snapshot bf
      ON bt.trading_date = bf.trading_date
    WHERE bt.source_event_type='backtest'
      AND bf.source_event_type='backtest_backfill'
""").fetchone()[0]
print('common dates (overlap):', result)

conn.close()
