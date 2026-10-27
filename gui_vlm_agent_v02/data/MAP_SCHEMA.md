# 地图数据格式（通用）

任意校园/园区只要按下面 JSON 写一份，就能换地图，**不用改代码**。

```json
{
  "meta": {
    "name": "地图名称（任意）",
    "crs": "local_meters",
    "description": "说明"
  },
  "pois": [
    {
      "id": "唯一英文id",
      "name": "中文名",
      "name_en": "English name",
      "type": "entrance|building|amenity|dorm|sports|landmark",
      "x": 0,
      "y": 0,
      "aliases": ["别名1", "别名2"]
    }
  ]
}
```

## 坐标系

- 默认 **本地米制平面坐标**（不是经纬度）
- 原点随便定（常见：南门 = (0,0)）
- `x` 向东为正，`y` 向北为正
- 距离用欧氏距离：`sqrt((x1-x2)^2 + (y1-y2)^2)` 米

## 若你有真实经纬度

可先用简单投影转成本地米（示例脚本见 `tools/latlon_to_local.py`），
或直接把经纬度当 x/y（仅小范围近似，误差可接受时）。

## 换地图

```bash
python demo.py --map data/你的地图.json --test
```
