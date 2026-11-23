"""Convert audited city cells into the tables used by the research package."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
BASE = Path(__file__).resolve().parent
PILOTS = {"370100": "济南", "310000": "上海", "320100": "南京", "330100": "杭州",
          "340100": "合肥", "330400": "嘉兴", "110000": "北京"}


def write_table(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path, default=BASE)
    parser.add_argument("--coverage", type=Path, default=BASE)
    parser.add_argument("--last-month", type=int, default=5)
    parser.add_argument("--first-year", type=int, choices=(2018, 2019, 2020), default=2020)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    monthly, exact, audits, monthly_coverage = [], [], [], []
    years = range(args.first_year, YEARS[-1] + 1)
    for year in years:
        base = args.cache
        with np.load(base / f"validated_{year}_cells.npz") as z:
            acc, cities = z["acc"], z["cities"]
        audit = json.loads((base / f"validated_{year}_audit.json").read_text(encoding="utf-8"))
        # Legacy 2019+ cell files have no origin metadata and start at 2019-01.
        origin_year = int(audit.get("month_index_origin_year", 2019))
        if not (origin_year <= year and (year - origin_year) * 12 + 12 < 128):
            raise ValueError(f"{year}: 月份槽原点无效: {origin_year}")
        audits.append({"year": year, **audit})
        coverage = json.loads((args.coverage / f"coverage_{year}.json").read_text(encoding="utf-8"))
        assert int(acc[:, 3].sum()) <= audit["ht_total"]
        for month in range(1, 13):
            offset = (year - 2000) * 12 + month - 1
            raw = coverage["month_rows"][offset]
            if not raw:
                continue
            monthly_coverage.append(dict(
                year=year, month=month, source_rows=raw,
                raw_city_code_present=coverage["month_city_ok"][offset],
                raw_industry_code_length5=coverage["month_ind4_ok"][offset]))
            for slot, city in enumerate(cities):
                row = acc[slot * 128 + (year - origin_year) * 12 + month]
                total, manufacturing, services, ht, stars, n_exact, em, es = map(int, row)
                assert ht == manufacturing + services and n_exact == em + es <= ht <= total
                if total == 0:
                    continue
                prefecture = city.endswith("00") and not city.endswith("0000")
                municipality = city in {"110000", "120000", "310000", "500000"}
                eligible = int(month <= args.last_month and (prefecture or municipality))
                # Province-direct county aggregates are kept in the monthly data only.
                if city[2:] == "9000":
                    eligible = 0
                idvars = dict(city_code=city, year=year, month=month, all_new=total,
                              coverage_ok=eligible)
                monthly.append(dict(**idvars, manufacturing=manufacturing, services=services,
                                    hightech=ht, partial_candidate=stars))
                exact.append(dict(**idvars, manufacturing=em, services=es, hightech=n_exact))
    pilot = []
    for code, name in PILOTS.items():
        for year in years:
            subset = [r for r in monthly if r["year"] == year and r["city_code"] == code
                      and r["coverage_ok"]]
            if len(subset) == args.last_month:
                pilot.append(dict(city_code=code, city=name, year=year,
                                  months=len(subset), **{k: sum(r[k] for r in subset)
                                  for k in ("all_new", "manufacturing", "services", "hightech")}))
    write_table(args.output / "城市月度统计.csv", monthly)
    write_table(args.output / "城市月度统计_仅四位小类.csv", exact)
    write_table(args.output / "七个试点城市同期统计.csv", pilot)
    write_table(args.output / "年度清洗审计.csv", audits)
    write_table(args.output / "原始记录月度覆盖.csv", monthly_coverage)


if __name__ == "__main__":
    main()
