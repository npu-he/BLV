"""单元测试：确定性空间工具"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spatial_tools import CampusMap, SpatialTools

MAP = Path(__file__).resolve().parents[1] / "data" / "campus_map.json"


def test_identify():
    tools = SpatialTools(CampusMap.from_json(MAP))
    r = tools.identify("图书馆")
    assert r["ok"] and r["matches"][0]["id"] == "library"
    r2 = tools.identify("不存在的地方xyz")
    assert not r2["ok"]


def test_distance_and_relation():
    tools = SpatialTools(CampusMap.from_json(MAP))
    d = tools.distance("南门", "图书馆")
    assert d["ok"] and d["distance_m"] > 100
    rel = tools.relation("图书馆", "南门")
    assert rel["ok"] and "direction" in rel


def test_nearby_and_compare():
    tools = SpatialTools(CampusMap.from_json(MAP))
    n = tools.nearby("图书馆", radius_m=100)
    assert n["ok"] and n["count"] >= 1
    c = tools.compare_distance("南门", "图书馆", "食堂")
    assert c["ok"] and c["closer"]["name"] in ("图书馆", "食堂", "学生食堂")


if __name__ == "__main__":
    test_identify()
    test_distance_and_relation()
    test_nearby_and_compare()
    print("all spatial tests passed")
