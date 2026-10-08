# 产线 schema 大表 · 索引

> 六条产线，每条一张 **产品级** 大表 + 一张 **系列级** 大表。**空表 = schema；填满 = 三元组**（`0_matrix_to_triples.py` 反向）。
> 目录：`input/<产线>/`
>   `schema_<产线>.csv`（元特性表，7 列制式）
>   `大表/大表_<产线>_{产品级,系列级}.csv`（填）
>   `大表/模板_<产线>_{产品级,系列级}.csv`（空 = schema）

## 状态总览
| 产线 | 产品级列 | 系列级列 | 数据 | 状态 |
|---|---|---|---|---|
| 手机 | 40 | 6 | 6 款（Mate） | ✅ schema + 已映射填充 |
| 耳机 | 29 | 6 | 20 款 | schema ✅；填充**待映射**（数据列名未统一） |
| 笔记本 | 23 | 6 | 9 款 | schema ✅；填充待映射 |
| 手表 | 28 | 6 | 10 款 | schema ✅；填充待映射 |
| 平板 | 26 | 6 | 0 | schema ✅（先定列，后进数据） |
| 汽车 | 22 | 6 | 0 | schema ✅（先定列，后进数据） |

## 列的两条标注（见 D-12 / D-13）
- **来源** `[你定]/[数据]/[我拟]/[D-x]`：`[我拟]` 默认**存疑，待你确认**。
- **价值** `[价值:顶/高/中/低]`：**行序 = 列序 = 优先级**。

## 怎么改 / 怎么用
```powershell
# 1) 改优先级：编辑 schema 的 [价值:x]，或直接调行序，然后
python tools\0_sort_schema.py --schema input\手机\schema_手机.csv
# 2) 出空表(schema) / 填充
python tools\0_make_matrix.py --title 手机 --schema input\手机\schema_手机.csv --data input\手机\数据.jsonl --outdir input\手机\大表
# 3) 填完后回写三元组
python tools\0_matrix_to_triples.py --product input\手机\大表\大表_手机_产品级.csv --series input\手机\大表\大表_手机_系列级.csv --out-data input\手机\数据.jsonl
# 4) 整理建议（同义列/独有列）
python tools\0_analyze_matrix.py --data input\手机\数据.jsonl --out input\手机\整理建议_手机.md --title 手机
```

## 待办
- **耳机/笔记本/手表**：数据列名 → schema 列名 **映射**（如 耳机 `降噪深度（峰值）/（平均）` → `降噪深度`；`防漏音技术/频响范围/…` → `特性`）。需要一个 `--rename` 映射表（可加进 `0_make_matrix.py`）。
- **平板/汽车**：先把 schema 定稿，再进数据/三元组。
- **`[我拟]` 列**：逐条请你拍（留/删/改）。
