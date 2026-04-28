import sqlite3, os
conn = sqlite3.connect('data/orca_state.db')

print('=== Final Status ===')
print('lessons:', conn.execute('SELECT COUNT(1) FROM candidate_lessons').fetchone()[0])
print('orphan:', conn.execute('SELECT COUNT(1) FROM candidate_lessons WHERE context_snapshot_id IS NULL').fetchone()[0])

print('')
print('=== Snapshot sources ===')
rows = conn.execute("""
    SELECT source_event_type, COUNT(1) 
    FROM lesson_context_snapshot 
    GROUP BY source_event_type
""").fetchall()
for r in rows:
    print(r)

print('')
print('=== DB ===')
print('size MB:', round(os.path.getsize('data/orca_state.db') / 1024 / 1024, 2))

conn.close()
