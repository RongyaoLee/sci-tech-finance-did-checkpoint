"""Build a common-calendar-window panel and estimate policy effects."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t


YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
COUNTS = ("manufacturing", "services", "all_new")
POLICY_CODES = {"济南": "370100", "上海": "310000", "南京": "320100",
                "杭州": "330100", "合肥": "340100", "嘉兴": "330400",
                "北京": "110000"}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def code(value):
    key = value.strip()
    if len(key) == 4 and key.isascii() and key.isdecimal():
        key += "00"
    if len(key) != 6 or not key.isascii() or not key.isdecimal():
        raise ValueError(f"地级市代码格式有误: {value!r}")
    return key


def load_population(path):
    population = {}
    for record in read_csv(path) if path else []:
        key = code(record["city_code"])
        value = float(record["population_2020"])
        if key in population or not np.isfinite(value) or value <= 0:
            raise ValueError(f"人口数无效或城市重复: {key}")
        population[key] = value
    return population


def build_panel(monthly, policy, population, last_month=8, years=YEARS):
    months = set(range(1, last_month + 1))
    timing = {POLICY_CODES[row["city"]]: (int(row["transition_year"]),
              int(row["first_full_treatment_year"])) for row in policy}
    if set(timing) != set(POLICY_CODES.values()) or len(policy) != len(timing):
        raise ValueError("政策表应有全部七个试点城市且每市唯一")
    cells = defaultdict(dict)
    seen = set()
    for row in monthly:
        year, month = int(row["year"]), int(row["month"])
        if year not in years or month not in months:
            continue
        city = code(row["city_code"])
        key = (city, year, month)
        if key in seen:
            raise ValueError(f"重复城市月份: {key}")
        seen.add(key)
        if row.get("coverage_ok", "1").strip() != "1":
            cells[city, year]
            continue
        counts = tuple(int(row[name]) for name in COUNTS)
        if min(counts) < 0 or sum(counts[:2]) > counts[2]:
            raise ValueError(f"企业计数矛盾: {key}")
        cells[city, year][month] = counts

    panel, audit = [], []
    city_codes = sorted(set(timing) | {city for city, _ in cells})
    for city, year in ((city, year) for city in city_codes for year in years):
        monthly_counts = cells.get((city, year), {})
        transition, cohort = timing.get(city, (None, None))
        use = year != transition and city != POLICY_CODES["北京"]
        missing = months - monthly_counts.keys()
        audit.append(dict(city_code=city, year=year, usable_months=len(monthly_counts),
                          missing_months=",".join(map(str, sorted(missing))),
                          benchmark_eligible=int(use and not missing)))
        if missing:
            continue
        manufacturing, services, all_new = map(sum, zip(*monthly_counts.values()))
        hightech = manufacturing + services
        pop = population.get(city)
        panel.append(dict(city_code=city, year=year, manufacturing=manufacturing,
                          services=services, all_new=all_new, hightech=hightech,
                          hightech_per_10k=10000 * hightech / pop if pop else None,
                          all_new_per_10k=10000 * all_new / pop if pop else None,
                          hightech_share=hightech / all_new if all_new else None,
                          log_hightech=np.log1p(hightech),
                          transition_year=transition, cohort_year=cohort,
                          treated=int(cohort is not None and year >= cohort),
                          benchmark_eligible=int(use)))
    return panel, audit


def twfe(sample, outcome):
    cities = sorted({row["city_code"] for row in sample})
    years = sorted({row["year"] for row in sample})
    if len(cities) < 2 or len(years) < 2:
        return None
    where = np.array([cities.index(row["city_code"]) for row in sample])
    x = np.column_stack([
        np.array([row["treated"] for row in sample]),
        np.eye(len(cities))[where],
        np.array([[row["year"] == year for year in years[1:]] for row in sample]),
    ])
    y = np.array([row[outcome] for row in sample])
    coefficient, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank < x.shape[1] or len(y) <= rank:
        return None
    residual = y - x @ coefficient
    # First row of the pseudoinverse supplies weights for the treatment coefficient.
    weights = np.linalg.pinv(x)[0]
    scores = np.bincount(where, weights=weights * residual, minlength=len(cities))
    clusters = len(cities)
    correction = clusters / (clusters - 1) * (len(y) - 1) / (len(y) - rank)
    se = np.sqrt(correction * (scores @ scores))
    return dict(outcome=outcome, estimate=coefficient[0], cluster_se=se,
                conventional_p=2 * student_t.sf(abs(coefficient[0] / se), clusters - 1)
                if se > 0 else None, observations=len(y), city_clusters=clusters,
                treated_cities=len({row["city_code"] for row in sample if row["treated"]}))


def group_effects(sample, outcome, years=YEARS):
    by_city = defaultdict(dict)
    for row in sample:
        by_city[row["city_code"]][row["year"]] = row
    for cohort, base in ((2022, 2020), (2023, 2021)):
        for year in years:
            # Earlier available endpoint is a placebo; the announcement year stays out.
            if year == base or year == cohort - 1:
                continue
            treated, controls = [], []
            for observations in by_city.values():
                if base not in observations or year not in observations:
                    continue
                row = observations[year]
                delta = row[outcome] - observations[base][outcome]
                if row["cohort_year"] == cohort:
                    treated.append(delta)
                elif row["cohort_year"] is None:
                    controls.append(delta)
            if treated and controls:
                yield dict(outcome=outcome, cohort_year=cohort, year=year, baseline_year=base,
                           comparison="pre_policy" if year < base else "post_policy",
                           estimate=np.mean(treated) - np.mean(controls),
                           treated_cities=len(treated), comparison_cities=len(controls))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("monthly", type=Path)
    parser.add_argument("--policy", type=Path, default=Path(__file__).with_name("试验区政策时间表_核实重采.csv"))
    parser.add_argument("--population", type=Path)
    parser.add_argument("--first-year", type=int, choices=(2018, 2019, 2020), default=2020)
    parser.add_argument("--last-month", type=int, choices=range(1, 13), default=8)
    parser.add_argument("--balanced", action="store_true",
                        help="保留所有非过渡年均有同期数据的城市")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("请给本次运行指定一个空输出目录")
    args.output.mkdir(exist_ok=True, parents=True)
    years = tuple(range(args.first_year, YEARS[-1] + 1))
    panel, audit = build_panel(read_csv(args.monthly), read_csv(args.policy),
                               load_population(args.population), args.last_month, years)
    write_csv(args.output / "覆盖审计.csv", audit)
    write_csv(args.output / "同期城市面板.csv", panel)
    candidates = [row for row in panel if row["benchmark_eligible"]]
    if args.balanced:
        availability = defaultdict(set)
        for row in candidates:
            availability[row["city_code"]].add(row["year"])
        candidates = [row for row in candidates if availability[row["city_code"]]
                      == set(years) - {row["transition_year"]}]
    baseline, cohort_results, missing, leave_one_out = [], [], [], []
    for outcome in ("hightech_per_10k", "hightech", "log_hightech", "manufacturing",
                    "services", "hightech_share", "all_new_per_10k"):
        complete = [row for row in candidates if row[outcome] is not None]
        missing.append(dict(outcome=outcome, eligible=len(candidates), used=len(complete)))
        if estimate := twfe(complete, outcome):
            baseline.append(estimate)
        cohort_results.extend(group_effects(complete, outcome, years))
        if outcome == "hightech_per_10k":
            for city_name, city in POLICY_CODES.items():
                if not any(r["city_code"] == city and r["treated"] for r in complete):
                    continue
                reduced = [row for row in complete if row["city_code"] != city]
                if estimate := twfe(reduced, outcome):
                    leave_one_out.append({"excluded_city": city_name, **estimate})
    write_csv(args.output / "各结果变量样本量.csv", missing)
    write_csv(args.output / "双向固定效应.csv", baseline)
    write_csv(args.output / "分批同期差分.csv", cohort_results)
    write_csv(args.output / "处理城市逐一剔除.csv", leave_one_out)
    print(f"形成 {len(panel)} 个城市—年度观测，TWFE {len(baseline)} 项，分批差分 {len(cohort_results)} 项。")


if __name__ == "__main__":
    main()
