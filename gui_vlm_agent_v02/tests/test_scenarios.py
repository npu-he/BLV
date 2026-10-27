"""对照 PPT 五个工作场景的冒烟测试。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import build_default_agent
from spatial_tools import SpatialTools, CampusMap, dispatch_tool

MAP = Path(__file__).resolve().parents[1] / "data" / "campus_map.json"


def test_tools_ppt():
    tools = SpatialTools(CampusMap.from_json(MAP))
    assert tools.identify("图书馆")["ok"]
    assert tools.get_position("图书馆")["ok"]
    assert tools.relation("图书馆", "南门")["ok"]
    assert tools.distance("南门", "图书馆")["ok"]
    assert tools.nearby("图书馆")["ok"]
    assert tools.list_pois()["ok"]
    print("[OK] PPT 六工具均可用")


def test_five_scenarios():
    a = build_default_agent("rule")
    # 01 Object grounding
    r = a.chat("图书馆是什么")
    assert "图书馆" in r or "地图" in r
    print("[01 对象识别]", r[:60])

    a.chat("我在南门。")
    # 02 Spatial relation
    r = a.chat("图书馆在哪？")
    assert "米" in r and ("东" in r or "南" in r or "西" in r or "北" in r)
    print("[02 空间关系]", r)

    # 03 Map exploration
    r = a.chat("图书馆附近有什么？")
    assert "范围内" in r or "附近" in r or "处" in r
    print("[03 地图探索]", r[:80])

    # 04 Spatial comparison
    r = a.chat("图书馆和食堂哪个离南门更近？")
    assert "更近" in r
    print("[04 空间比较]", r)

    # 05 State tracking
    r1 = a.chat("我在图书馆。")
    r2 = a.chat("体育馆在哪？")
    print("[05 状态跟踪]", r1, "|", r2[:60])
    assert a.user_location == "图书馆"
    print("全部场景冒烟通过")


if __name__ == "__main__":
    test_tools_ppt()
    test_five_scenarios()
