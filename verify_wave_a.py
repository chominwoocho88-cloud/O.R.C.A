import sqlite3

conn = sqlite3.connect('data/orca_state.db')

print('=' * 60)
print('Wave A Final Verification')
print('=' * 60)

print()
print('[1] candidate_registry by source_event_type:')
for row in conn.execute('SELECT source_event_type, COUNT(*) FROM candidate_registry GROUP BY source_event_type'):
    print(f'   {row[0]}: {row[1]}')

print()
total_outcomes = conn.execute('SELECT COUNT(*) FROM candidate_outcomes').fetchone()[0]
print(f'[2] candidate_outcomes: {total_outcomes}')

total_lessons = conn.execute('SELECT COUNT(*) FROM candidate_lessons').fetchone()[0]
print(f'[3] candidate_lessons: {total_lessons}')

print()
print('[4] signal_family distribution (backtest only):')
for row in conn.execute("SELECT signal_family, COUNT(*) FROM candidate_registry WHERE source_event_type='backtest' GROUP BY signal_family ORDER BY COUNT(*) DESC"):
    print(f'   {row[0]}: {row[1]}')

print()
print('[5] source_session_id (backtest):')
for row in conn.execute("SELECT source_session_id, COUNT(*) FROM candidate_registry WHERE source_event_type='backtest' GROUP BY source_session_id"):
    sid = row[0][:30] if row[0] else 'NULL'
    print(f'   {sid}...: {row[1]}')

print()
date_stats = conn.execute("SELECT MIN(analysis_date), MAX(analysis_date), COUNT(DISTINCT analysis_date) FROM candidate_registry WHERE source_event_type='backtest'").fetchone()
print(f'[6] Date range: {date_stats[0]} ~ {date_stats[1]} ({date_stats[2]} days)')

print()
print('[7] backtest_sessions (latest 10):')
for row in conn.execute('SELECT system, session_id, started_at FROM backtest_sessions ORDER BY started_at DESC LIMIT 10'):
    print(f'   [{row[0]}] {row[1][:20]}... started {row[2]}')

print()
print('[8] outcome accuracy by horizon:')
for row in conn.execute("SELECT horizon_label, COUNT(*), SUM(CASE WHEN outcome_status='hit' THEN 1 ELSE 0 END) FROM candidate_outcomes GROUP BY horizon_label"):
    label, events, hits = row
    rate = (hits / events * 100) if events > 0 else 0
    print(f'   {label}: {events} events, {hits} hits ({rate:.1f}%)')

print()
print('=' * 60)
print('Verification complete')
print('=' * 60)
conn.close()
