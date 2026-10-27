"""打印地图 POI 与简易 ASCII 示意，方便人工核对回答是否正确。"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[0] if False else Path(__file__).resolve().parent))
# parent is gui_vlm_agent when run as python tools_map_view.py from that dir
sys.path.insert(0, str(Path(__file__).resolve().parent))

from spatial_tools import CampusMap, euclidean, bearing_deg, direction_label


def ascii_map(campus: CampusMap, width: int = 50, height: int = 28) -> str:
    pois = campus.all_pois()
    xs = [p.x for p in pois]
    ys = [p.y for p in pois]
    min_x, max_x = min(xs) - 20, max(xs) + 20
    min_y, max_y = min(ys) - 20, max(ys) + 20
    grid = [["·"] * width for _ in range(height)]

    def to_cell(x, y):
        cx = int((x - min_x) / (max_x - min_x + 1e-9) * (width - 1))
        cy = int((max_y - y) / (max_y - min_y + 1e-9) * (height - 1))  # y up
        return max(0, min(width - 1, cx)), max(0, min(height - 1, cy))

    labels = []
    for p in pois:
        cx, cy = to_cell(p.x, p.y)
        mark = p.name[0]
        grid[cy][cx] = mark
        labels.append(f"  {mark} = {p.name} ({p.x:.0f},{p.y:.0f})")

    lines = ["".join(row) for row in grid]
    return "北 ↑\n" + "\n".join(lines) + "\n" + "\n".join(labels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="data/campus_map.json")
    ap.add_argument("--from", dest="a", default=None, help="验算：从地点A")
    ap.add_argument("--to", dest="b", default=None, help="验算：到地点B")
    args = ap.parse_args()

    campus = CampusMap.from_json(args.map)
    print(f"地图文件: {args.map}")
    print(f"POI 数量: {len(campus.all_pois())}\n")
    print(f"{'ID':<16} {'名称':<12} {'类型':<10} {'x':>8} {'y':>8}")
    print("-" * 58)
    for p in campus.all_pois():
        print(f"{p.id:<16} {p.name:<12} {p.type:<10} {p.x:>8.0f} {p.y:>8.0f}")

    print("\n=== ASCII 示意（仅相对位置）===")
    print(ascii_map(campus))

    if args.a and args.b:
        from spatial_tools import SpatialTools
        t = SpatialTools(campus)
        r = t.relation(args.a, args.b)
        d = t.distance(args.a, args.b)
        print("\n=== 验算 ===")
        print(d.get("message"))
        print(r.get("message"))


if __name__ == "__main__":
    main()
