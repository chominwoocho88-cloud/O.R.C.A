import sqlite3
conn = sqlite3.connect('data/orca_state.db')

print('=== Lessons in mismatch dates (2026-04-15~17) ===')
result = conn.execute("""
    SELECT s.trading_date, COUNT(l.lesson_id) as lessons
    FROM lesson_context_snapshot s
    LEFT JOIN candidate_lessons l ON l.context_snapshot_id = s.snapshot_id
    WHERE s.source_event_type='backtest'
      AND s.trading_date IN ('2026-04-15', '2026-04-16', '2026-04-17')
    GROUP BY s.trading_date
    ORDER BY s.trading_date
""").fetchall()
for r in result:
    print(r)

print('')
print('=== Total lessons in mismatch dates ===')
result = conn.execute("""
    SELECT COUNT(l.lesson_id)
    FROM lesson_context_snapshot s
    JOIN candidate_lessons l ON l.context_snapshot_id = s.snapshot_id
    WHERE s.source_event_type='backtest'
      AND s.trading_date IN ('2026-04-15', '2026-04-16', '2026-04-17')
""").fetchone()[0]
print('total:', result)

conn.close()
