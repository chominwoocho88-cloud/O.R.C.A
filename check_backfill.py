import sqlite3

conn = sqlite3.connect('data/orca_state.db')

print('=== Lessons linked to backfill snapshot ===')
result = conn.execute("""
    SELECT COUNT(1) FROM candidate_lessons l
    JOIN lesson_context_snapshot s ON l.context_snapshot_id = s.snapshot_id
    WHERE s.source_event_type='backtest_backfill'
""").fetchone()[0]
print('linked to backfill:', result)

print('')
print('=== Lessons linked to backtest snapshot ===')
result = conn.execute("""
    SELECT COUNT(1) FROM candidate_lessons l
    JOIN lesson_context_snapshot s ON l.context_snapshot_id = s.snapshot_id
    WHERE s.source_event_type='backtest'
""").fetchone()[0]
print('linked to backtest:', result)

print('')
print('=== Linked sum ===')
result = conn.execute("""
    SELECT COUNT(1) FROM candidate_lessons
    WHERE context_snapshot_id IS NOT NULL
""").fetchone()[0]
print('total linked:', result)

print('')
print('=== Snapshot link status ===')
rows = conn.execute("""
    SELECT s.source_event_type, 
           COUNT(DISTINCT s.snapshot_id) AS snapshots,
           COUNT(l.lesson_id) AS linked_lessons
    FROM lesson_context_snapshot s
    LEFT JOIN candidate_lessons l ON l.context_snapshot_id = s.snapshot_id
    GROUP BY s.source_event_type
""").fetchall()
for r in rows:
    print(r)

conn.close()
