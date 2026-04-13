"""
금융위원회 공공데이터 API 테스트 스크립트
GitHub Actions에서 수동 실행하여 오퍼레이션명 + 지수명 확인
"""
import os, httpx, json
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
KEY = os.environ.get("FSCAPI_KEY", "")
BASE = "https://apis.data.go.kr/1160100/service"

# 직전 거래일 계산
d = datetime.now(KST) - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
date_str = d.strftime("%Y%m%d")
print(f"조회일자: {date_str}")
print(f"키 설정: {'✅' if KEY else '❌ FSCAPI_KEY 미설정'}")
print()

def test(label, url, extra_params={}):
    params = {
        "serviceKey": KEY,
        "numOfRows": "5",
        "pageNo": "1",
        "resultType": "json",
        "basDd": date_str,
        **extra_params,
    }
    try:
        r = httpx.get(url, params=params, timeout=10)
        if r.status_code != 200:
            print(f"  [{label}] {r.status_code}: {r.text[:100]}")
            return
        j = r.json()
        body  = j.get("response", {}).get("body", {})
        total = body.get("totalCount", 0)
        items = body.get("items", {})
        item  = items.get("item", []) if isinstance(items, dict) else []
        items_list = item if isinstance(item, list) else [item]
        print(f"  [{label}] ✅ total={total}")
        if items_list:
            first = items_list[0]
            for k, v in list(first.items())[:6]:
                print(f"    {k}: {v}")
    except Exception as e:
        print(f"  [{label}] 실패: {e}")
    print()

print("=" * 50)
print("① VKOSPI 탐색 — 주가지수에서 idxNm 필터")
print("=" * 50)
# VKOSPI는 getStockMarketIndex 안에 idxNm으로 있을 가능성
params = {
    "serviceKey": KEY, "numOfRows": "5", "pageNo": "1",
    "resultType": "json", "basDd": date_str,
    "idxNm": "코스피변동성지수",
}
try:
    r = httpx.get(BASE + "/GetMarketIndexInfoService/getStockMarketIndex", params=params, timeout=10)
    j = r.json()
    items = j.get("response",{}).get("body",{}).get("items",{})
    item  = items.get("item",[]) if isinstance(items, dict) else []
    print(f"  idxNm=코스피변동성지수: total={j.get('response',{}).get('body',{}).get('totalCount',0)}")
    if item:
        first = item[0] if isinstance(item, list) else item
        for k,v in list(first.items())[:8]: print(f"    {k}: {v}")
except Exception as e:
    print(f"  실패: {e}")
print()

# VKOSPI 영문으로도 시도
for nm in ["VKOSPI", "변동성지수", "코스피200변동성지수"]:
    params2 = {**params, "idxNm": nm}
    try:
        r = httpx.get(BASE + "/GetMarketIndexInfoService/getStockMarketIndex", params=params2, timeout=8)
        total = r.json().get("response",{}).get("body",{}).get("totalCount",0)
        print(f"  idxNm={nm}: total={total}")
    except Exception as e:
        print(f"  idxNm={nm}: 실패")

print()
print("=" * 50)
print("② 기업재무정보 — 오퍼레이션명 탐색")
print("=" * 50)
# 삼성전자 crno
for op in ["getSummFinaStat", "getFundaStatInfo", "getCorpFinaInfo",
           "getStockFundamentals", "getCompFinaInfo"]:
    try:
        r = httpx.get(BASE + f"/GetFinaStatInfoService_V2/{op}",
            params={"serviceKey": KEY, "numOfRows": "1", "pageNo": "1",
                    "resultType": "json", "crno": "1301110006246"}, timeout=8)
        code = r.status_code
        total = r.json().get("response",{}).get("body",{}).get("totalCount","?") if code==200 else "?"
        print(f"  {op}: {code} total={total}")
    except Exception as e:
        print(f"  {op}: 실패")

print()
print("=" * 50)
print("③ 일반상품 — 원유 오퍼레이션명 탐색")
print("=" * 50)
for op in ["getCrudeOilPriceInfo", "getOilPriceInfo", "getCrudeOilInfo",
           "getEtcPriceInfo", "getGeneralProductPriceInfo"]:
    try:
        r = httpx.get(BASE + f"/GetGeneralProductInfoService/{op}",
            params={"serviceKey": KEY, "numOfRows": "1", "pageNo": "1",
                    "resultType": "json", "basDd": date_str}, timeout=8)
        code = r.status_code
        print(f"  {op}: {code}")
        if code == 200:
            items = r.json().get("response",{}).get("body",{}).get("items",{})
            item = items.get("item",[]) if isinstance(items, dict) else []
            if item:
                first = item[0] if isinstance(item, list) else item
                print(f"    샘플: {list(first.items())[:3]}")
    except Exception as e:
        print(f"  {op}: 실패")
