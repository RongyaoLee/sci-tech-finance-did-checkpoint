# 复现说明

推荐下载 source_bundle.zip，解压后在 source_bundle 目录运行。Python 3.11+，安装 requirements.txt；Stata 使用18（含 Mata），DTA 格式118。

```powershell
python -m pip install -r requirements.txt
python work/inspect_eps.py
python work/check_seven_cities.py
python work/estimate_harmonized_ddd.py
python work/estimate_harmonized_finance.py
```

依次在 Stata 运行 `do stata/main.do`、`do stata/cohort_models.do`。回到命令行：

```powershell
python work/validate_stata.py
```

验证脚本比较结果文件中的全部相关行；误差阈值1e-10。Python 输入 eps_city_panel.csv 与 Stata .dta 来自同一原始面板，转换不插补、不缩尾、不更改数值。DTA 的 cid 按中文城市名排序生成。

`python work/estimate_eps.py` 为先前分批次匹配及 SDID 扩展，会进行多次数值优化；`python work/estimate_patent_ddd.py` 会导入该模块后重估专利类型 DDD。此组及其它敏感性脚本与现有结果一起完整保留，不必为检查 Stata 一致性而全量运行。探索脚本名称中的 significance/short_run 代表过程记录，不表示预先注册的主分析。

公开专利网页重新采集入口：

```powershell
python crawlers/cnipa_grants.py
```

它抓取2020—2025年年报b2/b3/b4三个表，生成19城2017—2025年三类授权和逐数来源；产物写在 crawlers/，与归档 outputs/public_patents/ 对比后再使用。`work/build_public_patent_panel.py` 从已归档的 public_patent_source_rows.jsonl 还原申请人面板。历史专利下载器和高企名单爬虫见各目录，先运行对应脚本 --help 或阅读入口；并非所有一次性探测脚本都有CLI。

高企采集主入口为 `crawlers/enterprise/hn_crawler.py`，支持 --index/--pages、--parse/--limit、--status、--export；读取网站、下载PDF并解析可能依赖网络与外部工具。cert_lists/ 与 cert_hist/scripts/ 是实际恢复的城市历史补齐脚本。部分脚本保留历史相对路径及个别旧站点兼容处理，未重新全量抓取和验证。请在独立研究目录操作，保留原始网页/PDF与来源记录后再合并。缺失最终清洗面板须据原始资料重建，不能由模拟数据替代。

两个 do 文件也可在仓库根目录直接运行，它们会优先寻找 stata/ 下的数据，否则读取根目录同名 .dta。根目录版和压缩包版程序内容一致。
