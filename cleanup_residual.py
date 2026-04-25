import sqlite3

KEEP_JACKAL_PREFIX = 'bt_57ead7e7'
KEEP_ORCA_PREFIX = 'bt_f56a864f'

conn = sqlite3.connect('data/orca_state.db')

keep_jackal = conn.execute(
    "SELECT session_id FROM backtest_sessions WHERE system='jackal' AND session_id LIKE ?",
    (KEEP_JACKAL_PREFIX + '%',)
).fetchone()
keep_orca = conn.execute(
    "SELECT session_id FROM backtest_sessions WHERE system='orca' AND session_id LIKE ?",
    (KEEP_ORCA_PREFIX + '%',)
).fetchone()

if not keep_jackal:
    print('ERROR: JACKAL session not found')
    raise SystemExit(1)
if not keep_orca:
    print('ERROR: ORCA session not found')
    raise SystemExit(1)

keep_jackal_id = keep_jackal[0]
keep_orca_id = keep_orca[0]

print(f'Keeping JACKAL: {keep_jackal_id}')
print(f'Keeping ORCA: {keep_orca_id}')

print()
print('=== Before cleanup ===')
print('candidate_registry(backtest):', conn.execute("SELECT COUNT(*) FROM candidate_registry WHERE source_event_type='backtest'").fetchone()[0])
print('candidate_outcomes:', conn.execute('SELECT COUNT(*) FROM candidate_outcomes').fetchone()[0])
print('candidate_lessons:', conn.execute('SELECT COUNT(*) FROM candidate_lessons').fetchone()[0])
print('backtest_sessions:', conn.execute('SELECT COUNT(*) FROM backtest_sessions').fetchone()[0])

stale_candidate_ids = [row[0] for row in conn.execute(
    "SELECT candidate_id FROM candidate_registry WHERE source_event_type='backtest' AND source_session_id != ?",
    (keep_jackal_id,)
)]
print()
print(f'Stale candidate_ids to delete: {len(stale_candidate_ids)}')

if stale_candidate_ids:
    placeholders = ','.join('?' * len(stale_candidate_ids))
    deleted_outcomes = conn.execute(
        f'DELETE FROM candidate_outcomes WHERE candidate_id IN ({placeholders})',
        stale_candidate_ids
    ).rowcount
    print(f'Deleted outcomes: {deleted_outcomes}')

    deleted_lessons = conn.execute(
        f'DELETE FROM candidate_lessons WHERE candidate_id IN ({placeholders})',
        stale_candidate_ids
    ).rowcount
    print(f'Deleted lessons: {deleted_lessons}')

deleted_candidates = conn.execute(
    "DELETE FROM candidate_registry WHERE source_event_type='backtest' AND source_session_id != ?",
    (keep_jackal_id,)
).rowcount
print(f'Deleted candidates: {deleted_candidates}')

deleted_jackal = conn.execute(
    "DELETE FROM backtest_sessions WHERE system='jackal' AND session_id != ?",
    (keep_jackal_id,)
).rowcount
print(f'Deleted JACKAL sessions: {deleted_jackal}')

deleted_orca = conn.execute(
    "DELETE FROM backtest_sessions WHERE system='orca' AND session_id != ?",
    (keep_orca_id,)
).rowcount
print(f'Deleted ORCA sessions: {deleted_orca}')

conn.commit()

print()
print('=== After cleanup ===')
print('candidate_registry(backtest):', conn.execute("SELECT COUNT(*) FROM candidate_registry WHERE source_event_type='backtest'").fetchone()[0])
print('candidate_outcomes:', conn.execute('SELECT COUNT(*) FROM candidate_outcomes').fetchone()[0])
print('candidate_lessons:', conn.execute('SELECT COUNT(*) FROM candidate_lessons').fetchone()[0])
print('backtest_sessions:', conn.execute('SELECT COUNT(*) FROM backtest_sessions').fetchone()[0])

print()
print('=== Remaining sessions ===')
for row in conn.execute('SELECT system, session_id, started_at FROM backtest_sessions ORDER BY started_at DESC'):
    print(f'  [{row[0]}] {row[1][:30]}... {row[2]}')

print()
print('Running VACUUM...')
conn.execute('VACUUM')
print('VACUUM complete')

conn.close()
print()
print('Cleanup done!')
