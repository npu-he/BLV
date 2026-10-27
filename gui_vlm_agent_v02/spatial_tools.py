"""
GUI-VLM 确定性空间工具层
---------------------------------
原则：距离、方位、邻近关系一律由本模块计算，禁止 LLM 自行估算。
工具：identify / distance / relation / nearby / compare_distance
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------- 基础几何 ----------

def euclidean(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bearing_deg(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """从 a 指向 b 的方位角，0=北，90=东（本地坐标系 y 向上为正北）。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ang = math.degrees(math.atan2(dx, dy))  # atan2(x, y) → 相对正北
    return (ang + 360) % 360


def direction_label(deg: float) -> str:
    """8 方向中文标签。"""
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    idx = int((deg + 22.5) // 45) % 8
    return dirs[idx]


# ---------- 数据模型 ----------

@dataclass
class POI:
    id: str
    name: str
    name_en: str
    type: str
    x: float
    y: float
    aliases: List[str] = field(default_factory=list)
    lon: Optional[float] = None
    lat: Optional[float] = None

    @property
    def xy(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def matches(self, query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return False
        candidates = [self.name, self.name_en, self.id] + self.aliases
        return any(q in c.lower() or c.lower() in q for c in candidates)


class CampusMap:
    def __init__(self, pois: List[POI]):
        if not pois:
            raise ValueError("地图没有可查询的具名地点。")
        self.features = []
        self.meta = {}
        self.pois = {p.id: p for p in pois}
        self._by_name_index: List[POI] = list(pois)

    @classmethod
    def from_json(cls, path: str | Path) -> "CampusMap":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("type") == "FeatureCollection":
            from pyproj import Transformer
            project = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)
            pois = []
            for f in data.get("features", []):
                props, geom = f.get("properties", {}), f.get("geometry", {})
                if not props.get("name") or props.get("layer") in ("road", "boundary"):
                    continue
                if geom.get("type") == "Point":
                    lon, lat = geom["coordinates"]
                elif geom.get("type") == "Polygon":
                    ring = geom["coordinates"][0][:-1]
                    lon = sum(p[0] for p in ring) / len(ring)
                    lat = sum(p[1] for p in ring) / len(ring)
                else:
                    continue
                x, y = project.transform(lon, lat)
                tags = props.get("osm_tags", {})
                kind = "entrance" if tags.get("barrier") == "gate" else "building"
                if tags.get("amenity") in ("restaurant", "cafe", "hospital", "bus_station"): kind = "amenity"
                if tags.get("leisure"): kind = "sports"
                if tags.get("building") == "dormitory": kind = "dorm"
                pois.append(POI(id=props["id"], name=props["name"], name_en=tags.get("name:en", ""), type=kind, x=x, y=y, aliases=props.get("aliases", []), lon=lon, lat=lat))
            counts = {}
            for p in pois: counts[p.name] = counts.get(p.name, 0) + 1
            for p in pois:
                if counts[p.name] > 1:
                    original = p.name
                    p.name += "（" + p.id + "）"
                    p.aliases.append(original)
            campus = cls(pois)
            campus.features = data["features"]
            campus.meta = data.get("metadata", {})
            campus.meta["calculation_crs"] = "EPSG:32649"
            return campus
        pois = [POI(**item) for item in data["pois"]]
        campus = cls(pois)
        campus.meta = data.get("meta", {})
        return campus

    def all_pois(self) -> List[POI]:
        return list(self.pois.values())

    def get(self, poi_id: str) -> Optional[POI]:
        return self.pois.get(poi_id)


# ---------- 工具实现 ----------

class SpatialTools:
    """对外暴露给 Agent 的确定性工具。"""

    def __init__(self, campus: CampusMap, nearby_threshold_m: float = 120.0):
        self.campus = campus
        self.nearby_threshold_m = nearby_threshold_m

    # ---- identify ----
    def identify(self, query: str) -> Dict[str, Any]:
        """
        将用户提到的名称/别名解析为地图实体。
        返回：匹配的 POI 列表（可能 0/1/多个）。
        """
        q = query.strip().casefold()
        exact = [p for p in self.campus.all_pois() if q in [v.casefold() for v in [p.id, p.name, p.name_en] + p.aliases if v]]
        hits = exact or [p for p in self.campus.all_pois() if p.matches(query)]
        if not hits:
            return {
                "ok": False,
                "query": query,
                "matches": [],
                "message": f"地图中未找到与「{query}」匹配的地点。",
            }
        return {
            "ok": True,
            "query": query,
            "matches": [
                {
                    "id": p.id,
                    "name": p.name,
                    "type": p.type,
                    "x": p.x,
                    "y": p.y,
                }
                for p in hits
            ],
            "message": f"解析到 {len(hits)} 个匹配实体。",
        }

    def _resolve_one(self, query: str) -> Optional[POI]:
        res = self.identify(query)
        if not res["ok"] or len(res["matches"]) != 1:
            return None
        return self.campus.get(res["matches"][0]["id"])

    # ---- get_position ----
    def get_position(self, query: str) -> Dict[str, Any]:
        """返回地点在地图上的坐标与类型（PPT 工具②）。"""
        poi = self._resolve_one(query)
        if poi is None:
            ident = self.identify(query)
            if not ident["ok"]:
                return {"ok": False, "message": ident["message"]}
            if len(ident["matches"]) > 1:
                names = "、".join(m["name"] for m in ident["matches"])
                return {
                    "ok": False,
                    "message": f"「{query}」不唯一，可能是：{names}。请确认后再查位置。",
                }
            poi = self.campus.get(ident["matches"][0]["id"])
        return {
            "ok": True,
            "id": poi.id,
            "name": poi.name,
            "type": poi.type,
            "x": poi.x,
            "y": poi.y,
            "message": f"{poi.name} 的地图坐标为 ({poi.x:.0f}, {poi.y:.0f})，类型：{poi.type}。",
        }

    # ---- distance ----
    def distance(self, a: str, b: str) -> Dict[str, Any]:
        """两点直线距离（米）。"""
        pa, pb = self._resolve_one(a), self._resolve_one(b)
        if pa is None or pb is None:
            return {
                "ok": False,
                "message": f"无法唯一解析地点：a=「{a}」, b=「{b}」。请先用 identify 确认。",
            }
        d = euclidean(pa.xy, pb.xy)
        return {
            "ok": True,
            "from": {"id": pa.id, "name": pa.name},
            "to": {"id": pb.id, "name": pb.name},
            "distance_m": round(d, 1),
            "message": f"{pa.name} 到 {pb.name} 直线距离约 {round(d, 1)} 米。",
        }

    # ---- relation ----
    def relation(self, a: str, b: str) -> Dict[str, Any]:
        """
        a 相对 b 的空间关系：距离 + 方位。
        例如：图书馆在南门的东北方向，约 216 米。
        """
        pa, pb = self._resolve_one(a), self._resolve_one(b)
        if pa is None or pb is None:
            return {
                "ok": False,
                "message": f"无法唯一解析地点：a=「{a}」, b=「{b}」。",
            }
        d = euclidean(pa.xy, pb.xy)
        if d < 0.01:
            return {"ok": True, "subject": {"id": pa.id, "name": pa.name}, "reference": {"id": pb.id, "name": pb.name}, "distance_m": 0.0, "bearing_deg": None, "direction": "同一位置", "message": f"{pa.name}与{pb.name}是同一位置，距离为0米，无相对方位。"}
        deg = bearing_deg(pb.xy, pa.xy)  # 从 b 看 a
        label = direction_label(deg)
        return {
            "ok": True,
            "subject": {"id": pa.id, "name": pa.name},
            "reference": {"id": pb.id, "name": pb.name},
            "distance_m": round(d, 1),
            "bearing_deg": round(deg, 1),
            "direction": label,
            "message": f"{pa.name} 在 {pb.name} 的{label}方向，约 {round(d, 1)} 米。",
        }

    # ---- nearby ----
    def nearby(self, center: str, radius_m: Optional[float] = None, top_k: int = 5) -> Dict[str, Any]:
        """找出 center 附近的其他 POI。"""
        pc = self._resolve_one(center)
        if pc is None:
            return {"ok": False, "message": f"无法唯一解析中心点「{center}」。"}
        r = radius_m if radius_m is not None else self.nearby_threshold_m
        if not isinstance(r, (int, float)) or not math.isfinite(r) or r < 0 or not isinstance(top_k, int) or not 1 <= top_k <= 100:
            return {"ok": False, "message": "半径必须为非负有限数，top_k必须为1到100的整数。"}
        candidates = []
        for p in self.campus.all_pois():
            if p.id == pc.id:
                continue
            d = euclidean(pc.xy, p.xy)
            if d <= r:
                deg = bearing_deg(pc.xy, p.xy)
                candidates.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "type": p.type,
                        "distance_m": round(d, 1),
                        "direction": direction_label(deg),
                    }
                )
        candidates.sort(key=lambda x: x["distance_m"])
        top = candidates[:top_k]
        names = "、".join(c["name"] for c in top) if top else "无"
        return {
            "ok": True,
            "center": {"id": pc.id, "name": pc.name},
            "radius_m": r,
            "count": len(candidates),
            "nearby": top,
            "message": f"{pc.name} {r} 米范围内共 {len(candidates)} 处地点，最近的有：{names}。",
        }

    # ---- compare_distance ----
    def compare_distance(self, target: str, a: str, b: str) -> Dict[str, Any]:
        """比较 a、b 哪个离 target 更近。"""
        pt = self._resolve_one(target)
        pa, pb = self._resolve_one(a), self._resolve_one(b)
        if None in (pt, pa, pb):
            return {
                "ok": False,
                "message": f"无法唯一解析：target=「{target}」, a=「{a}」, b=「{b}」。",
            }
        da = euclidean(pt.xy, pa.xy)
        db = euclidean(pt.xy, pb.xy)
        if abs(da - db) < 0.05:
            return {"ok": True, "target": {"id": pt.id, "name": pt.name}, "a": {"id": pa.id, "name": pa.name, "distance_m": round(da,1)}, "b": {"id": pb.id, "name": pb.name, "distance_m": round(db,1)}, "tie": True, "message": f"相对{pt.name}，{pa.name}与{pb.name}的直线距离相同，约{da:.1f}米。"}
        closer = pa if da <= db else pb
        farther = pb if da <= db else pa
        return {
            "ok": True,
            "target": {"id": pt.id, "name": pt.name},
            "a": {"id": pa.id, "name": pa.name, "distance_m": round(da, 1)},
            "b": {"id": pb.id, "name": pb.name, "distance_m": round(db, 1)},
            "closer": {"id": closer.id, "name": closer.name},
            "message": f"相对{pt.name}，{closer.name}更近（{round(min(da, db), 1)} 米），"
                       f"{farther.name}更远（{round(max(da, db), 1)} 米）。",
        }

    # ---- list_all (辅助) ----
    def list_pois(self, poi_type: Optional[str] = None) -> Dict[str, Any]:
        items = self.campus.all_pois()
        if poi_type:
            items = [p for p in items if p.type == poi_type]
        names = "、".join(p.name for p in items[:12])
        more = f" 等共 {len(items)} 处" if len(items) > 12 else f"，共 {len(items)} 处"
        return {
            "ok": True,
            "count": len(items),
            "pois": [{"id": p.id, "name": p.name, "type": p.type} for p in items],
            "message": f"地图上有：{names}{more}" + (f"（类型={poi_type}）" if poi_type else "") + "。",
        }


# ---------- 工具 schema（给 LLM function-calling 用） ----------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "identify",
            "description": "将用户提到的地点名称解析为地图中的唯一实体。回答任何空间问题前应先调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用户提到的地点名或别名"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_position",
            "description": "查询地点在结构化地图上的坐标与类型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "地点名称"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "distance",
            "description": "计算两个地点之间的直线距离（米）。禁止自行估算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "string", "description": "地点A名称"},
                    "b": {"type": "string", "description": "地点B名称"},
                },
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "relation",
            "description": "查询地点A相对于地点B的方位与距离（如「图书馆在南门的东北方向」）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "string", "description": "目标地点"},
                    "b": {"type": "string", "description": "参考地点"},
                },
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nearby",
            "description": "查询某地点附近有哪些其他地点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "center": {"type": "string", "description": "中心地点名称"},
                    "radius_m": {"type": "number", "description": "半径（米），默认120"},
                    "top_k": {"type": "integer", "description": "返回最近的前k个，默认5"},
                },
                "required": ["center"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_distance",
            "description": "比较两个地点哪个离目标更近（如「图书馆和食堂哪个离南门更近」）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "参考目标"},
                    "a": {"type": "string", "description": "候选A"},
                    "b": {"type": "string", "description": "候选B"},
                },
                "required": ["target", "a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pois",
            "description": "列出地图上所有地点，可按类型过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "poi_type": {
                        "type": "string",
                        "description": "可选：entrance/building/amenity/dorm/sports/landmark",
                    }
                },
                "required": [],
            },
        },
    },
]


def dispatch_tool(tools: SpatialTools, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """统一分发工具调用。"""
    fn = getattr(tools, name, None) if name in {s["function"]["name"] for s in TOOL_SCHEMAS} else None
    if fn is None:
        return {"ok": False, "message": f"未知工具：{name}"}
    try:
        return fn(**arguments)
    except TypeError as e:
        return {"ok": False, "message": f"参数错误：{e}"}
