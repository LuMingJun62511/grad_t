"""
扩展产品数据: 从 2020 到 2026, 每个主要系列补到 4-5 代
"""

import json

EXISTING_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性.json"
OUT_PATH = r"D:\新建文件夹\grad_t\product_knowledge\data_\华为产品属性_扩展.json"

# 已有的产品名集合
with open(EXISTING_PATH, "r", encoding="utf-8") as f:
    existing = json.load(f)

existing_names = {p["name"] for p in existing}

def add(products, **kwargs):
    """只添加不重复的产品"""
    if kwargs["name"] not in existing_names:
        existing_names.add(kwargs["name"])
        products.append(kwargs)

new_products = []

# ============================================================
# Mate 系列 补 Mate 60, Mate 50, Mate 40
# ============================================================

# Mate 60 系列 (2023.08 发布)
add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 60 系列", name="Mate 60",
    alias=["M60", "Mate60"],
    positioning=["商务旗舰", "回归5G"],
    talking_points=["麒麟9000S", "6.69寸OLED直屏", "4750mAh", "卫星通信", "第二代昆仑玻璃"],
    generation="上上代", price="¥5499起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 60 系列", name="Mate 60 Pro",
    alias=["M60P", "Mate60 Pro"],
    positioning=["商务旗舰", "卫星通信旗舰"],
    talking_points=["麒麟9000S", "6.82寸LTPO", "5000mAh", "天通卫星通话", "第二代昆仑玻璃"],
    generation="上上代", price="¥6499起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 60 系列", name="Mate 60 Pro+",
    alias=["M60P+"],
    positioning=["商务旗舰", "顶配卫星通信"],
    talking_points=["麒麟9000S", "16GB内存", "双卫星通信", "天通+北斗"],
    generation="上上代", price="¥8999起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 60 系列", name="Mate 60 RS 非凡大师",
    alias=["M60RS", "首款非凡大师"],
    positioning=["超高端商务", "首款非凡大师品牌"],
    talking_points=["麒麟9000S", "陶瓷机身", "天通+北斗双卫星", "玄武钢化昆仑玻璃"],
    generation="上上代", price="¥11999起", status="在售")

# Mate 50 系列 (2022.09 发布)
add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 50 系列", name="Mate 50",
    alias=["M50"],
    positioning=["商务旗舰", "华为影像XMAGE首款"],
    talking_points=["骁龙8+ Gen1 4G", "6.7寸OLED", "4460mAh", "华为影像XMAGE", "北斗卫星消息"],
    generation="上上上代", price="¥4999起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 50 系列", name="Mate 50 Pro",
    alias=["M50P"],
    positioning=["商务旗舰", "影像旗舰"],
    talking_points=["骁龙8+ Gen1 4G", "6.74寸OLED", "4700mAh", "200倍变焦", "北斗卫星消息"],
    generation="上上上代", price="¥6799起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 50 系列", name="Mate 50 RS 保时捷设计",
    alias=["M50RS", "Mate50保时捷"],
    positioning=["超高端商务", "保时捷设计联名"],
    talking_points=["骁龙8+ Gen1 4G", "陶瓷机身", "200倍变焦", "超微距长焦"],
    generation="上上上代", price="¥12999起", status="在售")

# Mate 40 系列 (2020.10 发布)
add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 40 系列", name="Mate 40 Pro",
    alias=["M40P"],
    positioning=["商务旗舰", "麒麟绝唱"],
    talking_points=["麒麟9000 5G", "6.76寸OLED", "4400mAh", "66W快充", "徕卡影像", "星环设计"],
    generation="旧代", price="¥6499起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 40 系列", name="Mate 40 Pro+",
    alias=["M40P+"],
    positioning=["商务旗舰", "超大杯"],
    talking_points=["麒麟9000 5G", "12GB内存", "徕卡五摄", "100倍变焦", "陶瓷机身"],
    generation="旧代", price="¥8999起", status="在售")

add(new_products, company="华为", category="手机", series="Mate 系列",
    sub_series="Mate 40 系列", name="Mate 40 RS 保时捷设计",
    alias=["M40RS", "Mate40保时捷"],
    positioning=["超高端商务", "保时捷设计联名"],
    talking_points=["麒麟9000 5G", "陶瓷机身", "徕卡五摄", "测温功能"],
    generation="旧代", price="¥11999起", status="在售")


# ============================================================
# Pura/P 系列 补 P60, P50, P40, Pura 70
# ============================================================

# Pura 70 系列 (2024.04 发布, P系列更名Pura)
add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="Pura 70 系列", name="Pura 70",
    alias=["P70", "Pura70"],
    positioning=["影像旗舰", "P系列更名首作"],
    talking_points=["麒麟9010", "6.6寸OLED", "4900mAh", "50MP可变光圈", "第二代昆仑玻璃"],
    generation="中间代", price="¥5499起", status="在售")

add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="Pura 70 系列", name="Pura 70 Pro",
    alias=["P70P"],
    positioning=["影像旗舰", "专业影像"],
    talking_points=["麒麟9010", "6.8寸LTPO", "5050mAh", "100W快充", "50MP超聚光"],
    generation="中间代", price="¥6499起", status="在售")

add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="Pura 70 系列", name="Pura 70 Ultra",
    alias=["P70U"],
    positioning=["影像旗舰", "影像机皇"],
    talking_points=["麒麟9010", "1寸大底RYYB", "50MP可变光圈", "伸缩镜头", "100W快充"],
    generation="中间代", price="¥9999起", status="在售")

# P60 系列 (2023.03 发布)
add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="P60 系列", name="P60 Pro",
    alias=["P60P"],
    positioning=["影像旗舰", "超聚光夜视"],
    talking_points=["骁龙8+ Gen1 4G", "6.67寸LTPO", "4815mAh", "88W快充", "48MP超聚光主摄", "双向北斗卫星"],
    generation="旧代", price="¥6988起", status="在售")

add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="P60 系列", name="P60 Art",
    alias=["P60Art", "P60艺术版"],
    positioning=["影像旗舰", "艺术设计版"],
    talking_points=["骁龙8+ Gen1 4G", "海岛设计", "48MP超聚光", "88W快充", "5100mAh"],
    generation="旧代", price="¥8988起", status="在售")

# P50 系列 (2021.07 发布)
add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="P50 系列", name="P50 Pro",
    alias=["P50P"],
    positioning=["影像旗舰", "万象双环设计"],
    talking_points=["麒麟9000 4G/骁龙888 4G", "6.6寸OLED", "4360mAh", "66W快充", "50MP原色双影像", "200倍变焦"],
    generation="旧代", price="¥5988起", status="在售")

# P40 系列 (2020.03 发布)
add(new_products, company="华为", category="手机", series="Pura 系列",
    sub_series="P40 系列", name="P40 Pro+",
    alias=["P40P+"],
    positioning=["影像旗舰", "徕卡五摄"],
    talking_points=["麒麟990 5G", "6.58寸OLED", "4200mAh", "40W无线快充", "徕卡五摄", "100倍双目变焦", "陶瓷机身"],
    generation="旧代", price="¥7988起", status="在售")


# ============================================================
# 折叠屏 补 Mate X5, X3, X2
# ============================================================

add(new_products, company="华为", category="手机", series="折叠屏",
    sub_series="横向大折叠", name="Mate X5",
    alias=["X5"],
    positioning=["超高端商务", "横向大折叠"],
    talking_points=["麒麟9000S", "7.85寸内屏", "6.4寸外屏", "5060mAh", "双向北斗卫星", "玄武钢化昆仑玻璃"],
    generation="中间代", price="¥12999起", status="在售")

add(new_products, company="华为", category="手机", series="折叠屏",
    sub_series="横向大折叠", name="Mate X3",
    alias=["X3"],
    positioning=["超高端商务", "轻薄大折叠"],
    talking_points=["骁龙8+ Gen1 4G", "7.85寸内屏", "超薄铰链", "5060mAh", "IPX8防水", "双向北斗卫星"],
    generation="旧代", price="¥12999起", status="在售")

add(new_products, company="华为", category="手机", series="折叠屏",
    sub_series="横向大折叠", name="Mate X2",
    alias=["X2"],
    positioning=["超高端商务", "楔形设计"],
    talking_points=["麒麟9000 5G", "8寸内屏", "6.45寸外屏", "徕卡四摄", "100倍双目变焦", "楔形设计"],
    generation="旧代", price="¥17999起", status="在售")


# ============================================================
# nova 系列 补 nova 15, 14, 13
# ============================================================

add(new_products, company="华为", category="手机", series="nova 系列",
    sub_series="nova 15 系列", name="nova 15 Pro",
    alias=["n15P"],
    positioning=["中高端潮流", "nova影像旗舰"],
    talking_points=["麒麟9010S", "6.78寸OLED", "5000mAh", "100W快充"],
    generation="最新款", price="¥3699起", status="在售")

add(new_products, company="华为", category="手机", series="nova 系列",
    sub_series="nova 15 系列", name="nova 15 Ultra",
    alias=["n15U"],
    positioning=["中高端潮流", "nova全能旗舰"],
    talking_points=["麒麟9020", "一亿像素主摄", "100W快充", "卫星消息"],
    generation="最新款", price="¥4199起", status="在售")

add(new_products, company="华为", category="手机", series="nova 系列",
    sub_series="nova 14 系列", name="nova 14 Pro",
    alias=["n14P"],
    positioning=["中高端潮流", "nova人像旗舰"],
    talking_points=["麒麟9010", "6.78寸OLED", "4500mAh", "100W快充", "前置双摄"],
    generation="上代", price="¥3399起", status="在售")

add(new_products, company="华为", category="手机", series="nova 系列",
    sub_series="nova 14 系列", name="nova 14 Ultra",
    alias=["n14U"],
    positioning=["中高端潮流", "nova全能旗舰"],
    talking_points=["麒麟9010", "一亿像素主摄", "4900mAh"],
    generation="上代", price="¥3999起", status="在售")

add(new_products, company="华为", category="手机", series="nova 系列",
    sub_series="nova 13 系列", name="nova 13 Pro",
    alias=["n13P"],
    positioning=["中高端潮流", "nova自拍旗舰"],
    talking_points=["麒麟9000S", "6.7寸OLED", "4500mAh", "66W快充", "前置双摄"],
    generation="旧代", price="¥2999起", status="在售")


# ============================================================
# 畅享 补一代
# ============================================================

add(new_products, company="华为", category="手机", series="畅享系列",
    sub_series="畅享 80 系列", name="畅享 80 Pro",
    alias=["畅享80Pro"],
    positioning=["入门实用", "大屏续航"],
    talking_points=["麒麟710A 4G", "6.84寸", "7000mAh大电池", "NFC"],
    generation="上代", price="¥1399起", status="在售")


# ============================================================
# MatePad 补更早的 Pro
# ============================================================

add(new_products, company="华为", category="平板", series="MatePad Pro 系列",
    sub_series=None, name="MatePad Pro 11 2024",
    alias=["Pro11 2024"],
    positioning=["专业旗舰平板", "轻薄旗舰"],
    talking_points=["11寸OLED", "麒麟9000S", "8300mAh", "66W快充", "星闪连接"],
    generation="上代", price="¥4299起", status="在售")

add(new_products, company="华为", category="平板", series="MatePad Pro 系列",
    sub_series=None, name="MatePad Pro 12.6 2022",
    alias=["Pro12.6"],
    positioning=["专业旗舰平板", "大屏创作"],
    talking_points=["12.6寸OLED", "麒麟9000E", "10050mAh", "40W快充", "M-Pencil 2"],
    generation="旧代", price="¥4699起", status="在售")


# ============================================================
# WATCH 补更早的 GT
# ============================================================

add(new_products, company="华为", category="智能手表", series="WATCH GT 系列",
    sub_series=None, name="WATCH GT 5 Pro 46mm",
    alias=["GT5Pro"],
    positioning=["长续航户外旗舰", "专业运动"],
    talking_points=["钛合金表身", "蓝宝石玻璃", "14天续航", "高尔夫模式", "ECG"],
    generation="最新款", price="¥2488起", status="在售")

add(new_products, company="华为", category="智能手表", series="WATCH GT 系列",
    sub_series=None, name="WATCH GT 4 46mm",
    alias=["GT4"],
    positioning=["长续航运动", "时尚设计"],
    talking_points=["14天续航", "100+运动模式", "TruSeen 5.5+"],
    generation="旧代", price="¥1588起", status="在售")

add(new_products, company="华为", category="智能手表", series="WATCH GT 系列",
    sub_series=None, name="WATCH GT 3 Pro",
    alias=["GT3Pro"],
    positioning=["长续航旗舰", "首款陶瓷表"],
    talking_points=["陶瓷表圈", "钛合金/陶瓷机身", "14天续航", "ECG", "体温监测"],
    generation="旧代", price="¥2488起", status="在售")


# ============================================================
# FreeBuds 补更早的 Pro
# ============================================================

add(new_products, company="华为", category="耳机", series="FreeBuds Pro 系列",
    sub_series=None, name="FreeBuds Pro 3",
    alias=["Pro3", "星闪耳机"],
    positioning=["旗舰入耳降噪", "星闪连接"],
    talking_points=["星闪连接", "1.5Mbps无损传输", "智能动态降噪3.0", "47dB深度降噪"],
    generation="上代", price="¥1499", status="在售")

add(new_products, company="华为", category="耳机", series="FreeBuds Pro 系列",
    sub_series=None, name="FreeBuds Pro 2",
    alias=["Pro2"],
    positioning=["旗舰入耳降噪"],
    talking_points=["华为自研芯片", "47dB降噪", "双单元", "帝瓦雷调音"],
    generation="旧代", price="¥1299", status="在售")


# ============================================================
# 智慧屏 补
# ============================================================

add(new_products, company="华为", category="智慧屏", series="Vision 系列",
    sub_series=None, name="Vision 智慧屏 4 Pro",
    alias=["V4Pro"],
    positioning=["旗舰智慧屏", "AI摄像头"],
    talking_points=["MiniLED", "120Hz", "AI摄像头", "灵犀指向遥控", "75-85寸"],
    generation="旧代", price="¥8999起", status="在售")


# ============================================================
# 输出
# ============================================================

all_products = existing + new_products
print(f"原有: {len(existing)} 个产品")
print(f"新增: {len(new_products)} 个产品")
print(f"合计: {len(all_products)} 个产品")

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(all_products, f, ensure_ascii=False, indent=2)

print(f"已保存至: {OUT_PATH}")

# 按系列统计
from collections import Counter
series_count = Counter()
for p in all_products:
    series_count[f"{p['category']} > {p['series']} > {p.get('sub_series', '')}"] += 1

print("\n按子系列统计 SPU 数:")
for k, v in sorted(series_count.items()):
    if v >= 2:
        print(f"  {k}: {v} 个")
