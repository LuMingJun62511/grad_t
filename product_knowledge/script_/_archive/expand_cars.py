"""补全鸿蒙智行五大品牌的车型"""
import json

PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性_扩展.json"

with open(PATH, "r", encoding="utf-8") as f:
    existing = json.load(f)

existing_names = {p["name"] for p in existing}
new_products = []

def add(**kw):
    if kw["name"] not in existing_names:
        existing_names.add(kw["name"])
        new_products.append(kw)

# ================================================================
# 问界 (AITO) — 主力SUV品牌, 与赛力斯合作
# ================================================================
add(company="华为", category="智能汽车", series="问界", sub_series=None,
    name="问界 M9", alias=["M9", "问界旗舰"],
    positioning=["全尺寸SUV", "问界旗舰"],
    talking_points=["全尺寸6座SUV", "增程/纯电双版本", "华为ADS 3.0", "鸿蒙座舱4.0", "零重力座椅", "百万级底盘"],
    generation="最新款", price="¥46.98万起", status="在售")

add(company="华为", category="智能汽车", series="问界", sub_series=None,
    name="问界 M5", alias=["M5"],
    positioning=["中型SUV", "问界入门"],
    talking_points=["中型SUV", "增程/纯电双版本", "华为ADS 2.0", "鸿蒙座舱", "4秒级加速"],
    generation="在售", price="¥24.98万起", status="在售")

add(company="华为", category="智能汽车", series="问界", sub_series=None,
    name="问界 M5 EV", alias=["M5纯电"],
    positioning=["中型纯电SUV"],
    talking_points=["纯电SUV", "华为DriveONE电驱", "鸿蒙座舱", "620km续航"],
    generation="在售", price="¥28.98万起", status="在售")

add(company="华为", category="智能汽车", series="问界", sub_series=None,
    name="问界 M7 Pro", alias=["M7Pro"],
    positioning=["中大型SUV", "家庭旗舰"],
    talking_points=["中大型6座SUV", "增程动力", "华为ADS基础版", "鸿蒙座舱", "大空间"],
    generation="最新款", price="¥24.98万起", status="在售")

add(company="华为", category="智能汽车", series="问界", sub_series=None,
    name="问界 M7 Ultra", alias=["M7Ultra", "M7U"],
    positioning=["中大型SUV", "顶配旗舰"],
    talking_points=["中大型6座SUV", "华为ADS 3.0", "百万级底盘", "零重力座椅", "星环散射体"],
    generation="最新款", price="¥28.98万起", status="在售")


# ================================================================
# 智界 (Luxeed) — 轿跑品牌, 与奇瑞合作
# ================================================================
add(company="华为", category="智能汽车", series="智界", sub_series=None,
    name="智界 S7", alias=["S7初代", "智界首款"],
    positioning=["纯电轿跑", "智界首款"],
    talking_points=["纯电轿跑", "华为ADS 2.0", "鸿蒙座舱", "800V碳化硅平台", "3.3秒加速"],
    generation="旧代", price="¥24.98万起", status="在售")


# ================================================================
# 享界 (Stelato) — 豪华品牌, 与北汽合作
# ================================================================
add(company="华为", category="智能汽车", series="享界", sub_series=None,
    name="享界 S9", alias=["S9"],
    positioning=["豪华轿车", "行政旗舰"],
    talking_points=["豪华行政轿车", "华为ADS 3.0", "鸿蒙座舱4.0", "800V碳化硅", "空气悬架", "后排零重力"],
    generation="最新款", price="¥39.98万起", status="在售")


# ================================================================
# 尊界 (Maextro) — 超豪华品牌, 与江淮合作
# ================================================================
add(company="华为", category="智能汽车", series="尊界", sub_series=None,
    name="尊界 S800", alias=["S800", "尊界轿车"],
    positioning=["超豪华轿车", "尊界旗舰"],
    talking_points=["超豪华轿车", "百万级定位", "华为全栈技术", "L3级智驾", "行政后排"],
    generation="即将发布", price="¥100万起", status="即将发布")


# ================================================================
# 尚界 — 年轻品牌
# ================================================================
add(company="华为", category="智能汽车", series="尚界", sub_series=None,
    name="尚界 S5", alias=["S5", "尚界轿车"],
    positioning=["年轻轿跑", "尚界入门"],
    talking_points=["紧凑型轿跑", "华为ADS基础版", "鸿蒙座舱", "年轻化设计"],
    generation="最新款", price="¥15万起", status="在售")


# ================================================================
# 乾崑智驾
# ================================================================
add(company="华为", category="智能汽车", series="乾崑智驾", sub_series=None,
    name="乾崑智驾 ADS 4.0", alias=["ADS4.0", "华为智驾"],
    positioning=["智能驾驶系统", "L3级架构"],
    talking_points=["L3级自动驾驶架构", "累计搭载140万+辆车", "35款合作车型", "全国城区NCA", "泊车代驾"],
    generation="最新款", price="订阅制", status="在售")


# ================================================================
# 输出
# ================================================================
all_products = existing + new_products
print(f"原有: {len(existing)} 个")
print(f"新增汽车: {len(new_products)} 个")
print(f"合计: {len(all_products)} 个")

with open(PATH, "w", encoding="utf-8") as f:
    json.dump(all_products, f, ensure_ascii=False, indent=2)

# 汽车统计
cars = [p for p in all_products if p["category"] == "智能汽车"]
sers = {}
for c in cars:
    s = c["series"]
    sers[s] = sers.get(s, 0) + 1
print("\n=== 智能汽车 ===")
for s, n in sorted(sers.items()):
    models = [c["name"] for c in cars if c["series"] == s]
    print(f"  {s}: {n} 款 — {', '.join(models)}")
print(f"  总计: {len(cars)} 款")

print(f"\n=== 全品类总计: {len(all_products)} 个产品 ===")
