# 工商登记清洗与政策效应估计

运行环境为 Python 3.10+、NumPy 和 SciPy。生成 PDF 的步骤见研究包根目录。脚本不联网，不修改工商源文件。

## 从汇总复现回归

从研究包根目录执行。

```powershell
python .\代码\科创金融_企业进入估计.py .\结果与图表\城市月度统计.csv --policy .\代码\试验区政策时间表_核实重采.csv --population .\代码\population_2020.csv --last-month 5 --balanced --output .\复现结果
python .\代码\科创金融_企业进入估计.py .\结果与图表\城市月度统计_仅四位小类.csv --policy .\代码\试验区政策时间表_核实重采.csv --population .\代码\population_2020.csv --last-month 5 --balanced --output .\复现结果_仅四位小类
```

如果没有人口表，把 `--population` 及路径删去。脚本会生成计数、对数、行业分项和占比结果，并在样本量表中注明人口口径缺失。

## 从有权访问的原始压缩包重建

设 `$rawDir` 为原始分年压缩包所在目录，`$cache` 为有写入权限、空间足够的本地目录。各年 ZIP 逐一校验，经 `scan_stata.py` 提取必要字段。压缩数据全部读至文件尾校验 CRC。缓存包含企业标识，须存于本地。

```powershell
$rawDir = 'D:/registration_raw'
$cache = 'D:/registration_cache'
New-Item -ItemType Directory -Force $cache
foreach ($year in 2020..2023) {
    python .\代码\scan_stata.py "$rawDir/$year.dta.zip" "$cache/$year"
}
python .\代码\aggregate_window.py 2018 2019 2020 2021 2022 2023 --cache $cache --output "$cache/window" --last-month 5
python .\代码\package_tables.py .\复现汇总 --cache "$cache/window" --coverage .\代码\覆盖审计输入 --last-month 5
```

`scope_codes.json` 记录两个高技术产业分类与国民经济行业代码的对应。`gb4754_codes.csv` 用于校验原始行业代码及分类层级。待核验的带星号小类单报候选数。明细输出留在本地缓存目录。

`aggregate_window.py` 默认跳过信用代码中嵌入式 NUL 字节的判重。这类代码在部分原文件中是重复占位值；正常尾部 NUL 填充仍按有效代码判重。旧的 `--dedup-mode legacy` 仅供复核旧结果，不用于论文估计。

## 2023年城市代码补齐

先从同一原始登记文件抽取原省市字段和明码对照，再用严格阈值建立补码。在同名省市至少有100条明码锚点、主码占比至少98%、省份前缀与标准城市名核对通过时补齐。逐企业补码文件保留在受限缓存，不进入交付包。

```powershell
python .\代码\recover_2023_geography.py --meta "$cache/2023.json" --output "$cache/geography_2023"
python .\代码\conservative_2023_city_patch.py --cache $cache
python .\代码\aggregate_window.py 2020 2021 2022 2023 --cache $cache --output "$cache/window8" --last-month 8 --city-patch-2023 "$cache/geography_2023/conservative_city_patch.bin"
python .\代码\package_tables.py .\复现汇总_地理恢复 --cache "$cache/window8" --coverage .\代码\覆盖审计输入 --last-month 8
```

对补码汇总运行上面的估计命令，将月表路径替换为 `复现汇总_地理恢复` 中的对应文件，并使用 `--last-month 8 --balanced`。

延长政策前样本时，另读取并校验 `2019.dta.zip`，使用 `aggregate_window.py 2019 --cache $cache --output "$cache/window" --last-month 5` 建立2019年的城市单元。汇总和估计均加上 `--first-year 2019 --last-month 5`，估计保留 `--balanced` 参数。

## 论文与图

`论文原型.md` 是 PDF 的文本源稿。使用 Python 库 python-docx 执行 `python .\代码\render_paper.py .\代码\论文原型.md .\论文原型.docx`，再由 LibreOffice 或 Word 导出 PDF。核心图脚本使用 Pillow 与本机中文字体。


## 用 Stata 复算

在 Stata/MP 18 中进入本研究包根目录，执行以下命令。六组输入均为随包的 `同期城市面板.csv`，每组有七个结果变量。

```stata
do "代码/科创金融_复算.do"
```

命令文件按与 Python 相同的城市平衡条件及过渡年规则保留观测，估计城市与年份固定效应，标准误按城市聚类。原生回归结果、去除机器路径的运行摘要及对照表均在 `结果与图表/Stata复算/`。

## 2018—2023年扩展样本

六年期需先对2018—2023年各压缩包分别运行 `scan_stata.py`。随后以六个年份运行 `aggregate_window.py`，取 `--last-month 5`；`package_tables.py` 使用 `--first-year 2018 --last-month 5`。将估计脚本的输入改为相应月表，指定 `--balanced --first-year 2018 --last-month 5`。覆盖审计输入随包提供。两种行业口径各运行一次。
