import sqlite3
conn = sqlite3.connect("data/orca_state.db")

# Cluster 확인
cluster_count = conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0]
print(f"Clusters: {cluster_count}")

# Mapping 확인
mapping_count = conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0]
print(f"Mappings: {mapping_count}")

# Cached 확인
cached_count = conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot WHERE context_cluster_id IS NOT NULL").fetchone()[0]
print(f"Cached cluster IDs: {cached_count}/252")

# Cluster 별 size + label
print("\nClusters (sorted by size):")
print(f"{'cluster':10s} {'size':>5s} {'sil':>6s} {'regime':>10s}  label")
for row in conn.execute("""
    SELECT cluster_id, size, silhouette_score, dominant_regime, cluster_label 
    FROM lesson_clusters 
    ORDER BY size DESC
"""):
    cid_short = row[0].split('_')[-1] if '_' in row[0] else row[0][:8]
    print(f"  {cid_short:8s} {row[1]:5d} {row[2]:6.3f} {row[3]:>10s}  {row[4]}")

# Lesson 분포
print("\nLessons per cluster:")
print(f"{'cluster':10s} {'lessons':>8s}  label")
total = 0
for row in conn.execute("""
    SELECT lc.cluster_id, lc.cluster_label, COUNT(cl.candidate_id) as lessons
    FROM lesson_clusters lc
    LEFT JOIN lesson_context_snapshot lcs ON lcs.context_cluster_id = lc.cluster_id
    LEFT JOIN candidate_lessons cl ON cl.context_snapshot_id = lcs.snapshot_id
    GROUP BY lc.cluster_id, lc.cluster_label
    ORDER BY lessons DESC
"""):
    cid_short = row[0].split('_')[-1] if '_' in row[0] else row[0][:8]
    total += row[2]
    print(f"  {cid_short:8s} {row[2]:8d}  {row[1]}")
print(f"  {'TOTAL':8s} {total:8d}")

conn.close()
print("\n*** Wave F Phase 2 완성! ***")
