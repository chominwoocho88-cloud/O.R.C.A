import sqlite3
conn = sqlite3.connect("data/orca_state.db")
print("Sample 5 snapshots:")
for r in conn.execute("SELECT trading_date, regime, vix_level, sp500_momentum_5d, sp500_momentum_20d, dominant_sectors FROM lesson_context_snapshot ORDER BY trading_date LIMIT 5"):
    print(f"  {r[0]} regime={r[1]} vix={r[2]:.2f} sp500_5d={r[3]:.4f} sp500_20d={r[4]:.4f} sectors={r[5][:50]}")
print()
print("Last 5 snapshots:")
for r in conn.execute("SELECT trading_date, regime, vix_level, sp500_momentum_5d, sp500_momentum_20d, dominant_sectors FROM lesson_context_snapshot ORDER BY trading_date DESC LIMIT 5"):
    print(f"  {r[0]} regime={r[1]} vix={r[2]:.2f} sp500_5d={r[3]:.4f} sp500_20d={r[4]:.4f} sectors={r[5][:50]}")
conn.close()
