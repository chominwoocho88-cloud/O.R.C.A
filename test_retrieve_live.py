import sqlite3
import sys
sys.path.insert(0, '.')

from orca.lesson_retrieval import retrieve_similar_lessons_for_features

# 너의 현재 시장 상황 가정 (혹은 실제 값)
print("=" * 60)
print("Test 1: Risk-on bullish growth scenario")
print("=" * 60)

market_features = {
    'vix_level': 16.5,
    'sp500_momentum_5d': 0.012,
    'sp500_momentum_20d': 0.025,
    'nasdaq_momentum_5d': 0.018,
    'nasdaq_momentum_20d': 0.035,
    'regime': '위험선호',
    'dominant_sectors': ['Technology', 'Communication Services', 'Consumer Discretionary'],
}

lessons = retrieve_similar_lessons_for_features(
    features=market_features,
    top_k=5,
    quality_filter='high',
)

print(f"\nRetrieved {len(lessons)} lessons:")
print(f"\nCluster: {lessons[0].get('cluster_label') if lessons else 'N/A'}")

if lessons:
    win_count = sum(1 for l in lessons if l.get('lesson_value', 0) > 0)
    win_rate = win_count / len(lessons) if lessons else 0
    avg_value = sum(l.get('lesson_value', 0) for l in lessons) / len(lessons) if lessons else 0
    
    print(f"Win rate: {win_rate*100:.0f}%")
    print(f"Avg value: {avg_value:+.2f}%")
    print()
    print("Top lessons:")
    for i, l in enumerate(lessons, 1):
        print(f"  {i}. {l.get('ticker')} ({l.get('analysis_date', '')[:10]}): "
              f"{l.get('lesson_value', 0):+.2f}% "
              f"(peak {l.get('peak_pct', 0):+.2f}% day {l.get('peak_day', 0)}) "
              f"[{l.get('quality_tier')}]")

# Test 2: Risk-off scenario
print()
print("=" * 60)
print("Test 2: High VIX risk-off scenario")
print("=" * 60)

risk_off_features = {
    'vix_level': 28.0,
    'sp500_momentum_5d': -0.025,
    'sp500_momentum_20d': -0.045,
    'nasdaq_momentum_5d': -0.035,
    'nasdaq_momentum_20d': -0.055,
    'regime': '위험회피',
    'dominant_sectors': ['Energy', 'Utilities', 'Consumer Staples'],
}

lessons2 = retrieve_similar_lessons_for_features(
    features=risk_off_features,
    top_k=5,
    quality_filter='high',
)

print(f"\nRetrieved {len(lessons2)} lessons:")
print(f"\nCluster: {lessons2[0].get('cluster_label') if lessons2 else 'N/A'}")

if lessons2:
    win_count = sum(1 for l in lessons2 if l.get('lesson_value', 0) > 0)
    win_rate = win_count / len(lessons2) if lessons2 else 0
    avg_value = sum(l.get('lesson_value', 0) for l in lessons2) / len(lessons2) if lessons2 else 0
    
    print(f"Win rate: {win_rate*100:.0f}%")
    print(f"Avg value: {avg_value:+.2f}%")
    print()
    print("Top lessons:")
    for i, l in enumerate(lessons2, 1):
        print(f"  {i}. {l.get('ticker')} ({l.get('analysis_date', '')[:10]}): "
              f"{l.get('lesson_value', 0):+.2f}% [{l.get('quality_tier')}]")

print()
print("=" * 60)
print("✓ Wave F Phase 3 retrieve 정상 작동!")
print("=" * 60)
