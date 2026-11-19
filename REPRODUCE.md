# 复现说明

下载并解压 source_bundle.zip，在 `source_bundle` 目录中运行。Python 使用 3.11 或更高版本，Stata 程序已在 Stata/MP 18 上运行。

## 面板与估计

```powershell
python -m pip install -r requirements.txt
python work/inspect_eps.py
python work/check_seven_cities.py
python work/estimate_harmonized_ddd.py
python work/estimate_harmonized_finance.py
```

第一份脚本合并 EPS 导出表。专利授权以件计，GDP、贷款余额和财政科学支出以万元计。后面三份脚本分别估计七城专利匹配、申请人类型 DDD 和融资指标的变化。

在同一目录打开 Stata，运行两份 do 文件。

```stata
do stata/main.do
do stata/cohort_models.do
```

返回命令行，运行 `python work/validate_stata.py`。脚本将 Stata 输出与 Python 结果逐项比较，误差容限为 1e-10。两套程序使用同一份 EPS 面板原值，Stata 城市编号按城市名排序生成。

分批次匹配 DID 和 SDID 的入口为 `work/estimate_eps.py`。专利类型 DDD 的入口为 `work/estimate_patent_ddd.py`，该脚本会调用前者。探索性分析和相应结果也保存在 `work/`。

## 重新采集数据

运行 `python crawlers/cnipa_grants.py` 可从国家知识产权局 2020—2025 年统计年报的 b2、b3、b4 表提取三类专利授权数。脚本在 `crawlers/` 输出 19 城 2017—2025 年的授权数据及逐条来源，归档版本位于 `outputs/public_patents/`。申请人面板由 `work/build_public_patent_panel.py` 根据 `public_patent_source_rows.jsonl` 整理。

高企名单采集入口为 `crawlers/enterprise/hn_crawler.py`。用 `--index` 和 `--pages` 检索列表，用 `--parse` 和 `--limit` 解析文件，另有 `--status` 和 `--export` 选项。城市补录脚本位于该目录下的 `cert_lists/` 和 `cert_hist/scripts/`。部分旧脚本依赖采集时使用的目录、缓存和站点配置。
