import re
with open("orca/state.py", "r", encoding="utf-8") as f:
    content = f.read()

# clear_clustering_data 함수 찾기
match = re.search(r"def clear_clustering_data\(.*?\n(.*?)(?=\ndef |\Z)", content, re.DOTALL)
if match:
    func_body = match.group(0)
    print(func_body[:2000])  # 처음 2000자
else:
    print("Function not found!")
