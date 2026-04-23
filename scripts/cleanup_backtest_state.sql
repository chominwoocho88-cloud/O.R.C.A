-- Wave A-fix 2 cleanup script
-- WARNING: destructive. Back up data/orca_state.db before running.
--
-- PowerShell backup example:
--   Copy-Item data\orca_state.db data\orca_state.pre-wave-a-fix-2.db
--
-- Preview-only option:
--   Replace the final COMMIT; with ROLLBACK; before execution.
--   The preview SELECT statements below show the rows that will be removed.
--
-- Scope:
--   - Deletes JACKAL-owned backtest learning rows only
--   - Preserves ORCA walk-forward sessions and ORCA backtest state

PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS temp.tmp_jackal_backtest_candidates;
CREATE TEMP TABLE tmp_jackal_backtest_candidates AS
SELECT candidate_id
FROM candidate_registry
WHERE source_system = 'jackal'
  AND source_event_type = 'backtest';

DROP TABLE IF EXISTS temp.tmp_jackal_backtest_sessions;
CREATE TEMP TABLE tmp_jackal_backtest_sessions AS
SELECT session_id
FROM backtest_sessions
WHERE system = 'jackal';

SELECT 'preview.candidate_registry' AS label, COUNT(*) AS rows
FROM candidate_registry
WHERE candidate_id IN (SELECT candidate_id FROM tmp_jackal_backtest_candidates);

SELECT 'preview.candidate_outcomes' AS label, COUNT(*) AS rows
FROM candidate_outcomes
WHERE candidate_id IN (SELECT candidate_id FROM tmp_jackal_backtest_candidates);

SELECT 'preview.candidate_lessons' AS label, COUNT(*) AS rows
FROM candidate_lessons
WHERE candidate_id IN (SELECT candidate_id FROM tmp_jackal_backtest_candidates);

SELECT 'preview.backtest_sessions' AS label, COUNT(*) AS rows
FROM backtest_sessions
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

SELECT 'preview.backtest_pick_results' AS label, COUNT(*) AS rows
FROM backtest_pick_results
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

SELECT 'preview.backtest_daily_results' AS label, COUNT(*) AS rows
FROM backtest_daily_results
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

SELECT 'preview.backtest_state' AS label, COUNT(*) AS rows
FROM backtest_state
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

BEGIN TRANSACTION;

DELETE FROM candidate_lessons
WHERE candidate_id IN (SELECT candidate_id FROM tmp_jackal_backtest_candidates);

DELETE FROM candidate_outcomes
WHERE candidate_id IN (SELECT candidate_id FROM tmp_jackal_backtest_candidates);

DELETE FROM candidate_registry
WHERE candidate_id IN (SELECT candidate_id FROM tmp_jackal_backtest_candidates);

DELETE FROM backtest_pick_results
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

DELETE FROM backtest_daily_results
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

DELETE FROM backtest_state
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

DELETE FROM backtest_sessions
WHERE session_id IN (SELECT session_id FROM tmp_jackal_backtest_sessions);

SELECT 'post_delete.candidate_registry' AS label, COUNT(*) AS rows
FROM candidate_registry
WHERE source_system = 'jackal'
  AND source_event_type = 'backtest';

SELECT 'post_delete.backtest_sessions' AS label, COUNT(*) AS rows
FROM backtest_sessions
WHERE system = 'jackal';

COMMIT;
