"""Summarize the 2018–2023 common-window expansion from aggregate tables.

This script reads only published city-month and model CSVs.  It does not need
the row-level registration cache.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


PILOTS = {"370100": "济南", "310000": "上海", "320100": "南京",
          "330100": "杭州", "340100": "合肥", "330400": "嘉兴", "110000": "北京"}
COUNT_COLS = ("all_new", "manufacturing", "services", "hightech")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def counts(path, selected=None):
    out = defaultdict(lambda: defaultdict(int))
    for row in read(path):
        year, month = int(row["year"]), int(row["month"])
        if month > 5 or (selected is not None and row["city_code"] not in selected):
            continue
        key = (year, row["city_code"]) if selected is not None else year
        for name in COUNT_COLS:
            out[key][name] += int(row[name])
    return out


def model_rows(root, outcome):
    return {r["outcome"]: r for r in read(root / "双向固定效应.csv")}[outcome]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory
    main_nat = counts(root / "城市月度统计.csv")
    exact_nat = counts(root / "城市月度统计_仅四位小类.csv")
    main_pilot = counts(root / "城市月度统计.csv", PILOTS)
    exact_pilot = counts(root / "城市月度统计_仅四位小类.csv", PILOTS)
    cov = defaultdict(dict)
    for row in read(root / "原始记录月度覆盖.csv"):
        year = int(row["year"])
        if int(row["month"]) > 5:
            continue
        for key in ("source_rows", "raw_city_code_present", "raw_industry_code_length5"):
            cov[year][key] = cov[year].get(key, 0) + int(row[key])
    national = []
    for year in range(2018, 2024):
        m, e, c = main_nat[year], exact_nat[year], cov[year]
        assert m["all_new"] == e["all_new"] and m["hightech"] >= e["hightech"]
        national.append(dict(year=year, window="1—5月", all_new_city_coded=m["all_new"],
                             main_manufacturing=m["manufacturing"], main_services=m["services"],
                             main_hightech=m["hightech"], exact4_manufacturing=e["manufacturing"],
                             exact4_services=e["services"], exact4_hightech=e["hightech"],
                             main_share=m["hightech"] / m["all_new"],
                             exact4_share=e["hightech"] / e["all_new"],
                             raw_rows=c["source_rows"],
                             raw_city_code_rate=c["raw_city_code_present"] / c["source_rows"],
                             raw_four_digit_rate=c["raw_industry_code_length5"] / c["source_rows"]))
    pilot = []
    for year in range(2018, 2024):
        for code, name in PILOTS.items():
            m, e = main_pilot[year, code], exact_pilot[year, code]
            assert m["all_new"] == e["all_new"]
            pilot.append(dict(year=year, city_code=code, city=name,
                              all_new=m["all_new"], main_manufacturing=m["manufacturing"],
                              main_services=m["services"], main_hightech=m["hightech"],
                              exact4_manufacturing=e["manufacturing"],
                              exact4_services=e["services"], exact4_hightech=e["hightech"]))
    write(root / "全国同期统计_两种口径.csv", national)
    write(root / "七试点城市同期统计_两种口径.csv", pilot)

    lines = ["# 2018—2023年扩展样本", "", "共同窗口为每年1—5月；‘全国’汇总为有城市代码的登记记录。", "",
             "## 全国同期统计", "",
             "| 年 | 新设企业 | 主口径高技术 | 仅四位高技术 | 主口径占比 | 四位占比 | 原始记录城市代码率 |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for r in national:
        lines.append(f"| {r['year']} | {r['all_new_city_coded']:,} | {r['main_hightech']:,} | "
                     f"{r['exact4_hightech']:,} | {r['main_share']:.2%} | "
                     f"{r['exact4_share']:.2%} | {r['raw_city_code_rate']:.2%} |")
    lines += ["", "## 双向固定效应", "",
              "逐市和逐年固定效应；标准误按城市聚类。处理定义和过渡年处理沿用主研究包。", "",
              "| 行业口径 | 结果变量 | 系数 | 聚类标准误 | 常规p值 | 观测数 | 城市数 |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for category, folder in (("主口径", "主口径"), ("仅四位小类", "仅四位小类")):
        for outcome in ("hightech_per_10k", "hightech_share", "log_hightech", "hightech"):
            row = model_rows(root / folder, outcome)
            lines.append(f"| {category} | {outcome} | {float(row['estimate']):.6g} | "
                         f"{float(row['cluster_se']):.6g} | {float(row['conventional_p']):.4g} | "
                         f"{row['observations']} | {row['city_clusters']} |")
    lines += ["", "## 文件与复现", "",
              "原始2018压缩包经 `scan_stata.py` 流式扫描并校验ZIP CRC；本扩展只新建2018缓存，复用2019—2023已核验的城市月度单元。",
              "2018单元的月槽从1起算，审计JSON记录 `month_index_origin_year=2018`；旧单元缺该字段时按2019年起算。",
              "完整命令见本目录的 `复现说明.md`。", ""]
    (root / "扩展样本摘要.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
