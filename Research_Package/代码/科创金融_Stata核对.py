"""Compare Stata's native TWFE output with the packaged Python estimates.

Run this after ``do 科创金融_复算.do``. All paths are relative to this file.
"""

import csv
import math
from pathlib import Path


RESULTS = Path(__file__).resolve().parent.parent / "结果与图表"
STATA = RESULTS / "Stata复算" / "Stata_TWFE_原生结果.csv"
REPORT = RESULTS / "Stata复算" / "Stata与Python逐项核对.csv"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def reference_paths():
    sources = {
        "2020-2023": RESULTS,
        "2019-2023": RESULTS / "延长政策前样本",
    }
    extensions = []
    for directory in RESULTS.iterdir():
        panel = directory / "主口径" / "同期城市面板.csv"
        if not panel.is_file():
            continue
        years = {int(row["year"]) for row in read_csv(panel)}
        if min(years) == 2018 and max(years) == 2023:
            extensions.append(directory)
    if len(extensions) > 1:
        raise ValueError("Multiple 2018-2023 source directories were found")
    if extensions:
        sources["2018-2023"] = extensions[0]
    for window, directory in sources.items():
        yield window, "main", directory / "主口径"
        yield window, "four_digit", directory / "仅四位小类"


def main():
    reference = {}
    freshest_input = 0
    cases = 0
    for window, scope, directory in reference_paths():
        cases += 1
        for path in (directory / "同期城市面板.csv", directory / "双向固定效应.csv"):
            freshest_input = max(freshest_input, path.stat().st_mtime_ns)
        for row in read_csv(directory / "双向固定效应.csv"):
            key = (window, scope, row["outcome"])
            if key in reference:
                raise ValueError(f"Duplicate reference row: {key}")
            reference[key] = row

    stata_rows = read_csv(STATA)
    stale = STATA.stat().st_mtime_ns < freshest_input
    rows = []
    for stata in stata_rows:
        key = (stata["window"], stata["scope"], stata["outcome"])
        python = reference.pop(key)
        row = dict(window=key[0], scope=key[1], outcome=key[2])
        passed = True
        for field in ("estimate", "cluster_se", "conventional_p"):
            s, p = float(stata[field]), float(python[field])
            difference = abs(s - p)
            tolerance = 1e-10 if field == "conventional_p" else 1e-8
            passed &= math.isclose(s, p, rel_tol=1e-12, abs_tol=tolerance)
            row[f"stata_{field}"] = f"{s:.15g}"
            row[f"python_{field}"] = f"{p:.15g}"
            row[f"abs_diff_{field}"] = f"{difference:.9g}"
        for field in ("observations", "city_clusters", "treated_cities"):
            s, p = int(stata[field]), int(python[field])
            passed &= s == p
            row[f"stata_{field}"] = s
            row[f"python_{field}"] = p
        passed &= int(stata["df_r"]) == int(stata["city_clusters"]) - 1
        row["status"] = "PASS" if passed and not stale else "FAIL"
        rows.append(row)

    if reference:
        raise ValueError(f"Unmatched Python rows: {list(reference)[:5]}")
    if len(rows) != 7 * cases:
        raise ValueError(f"Expected {7 * cases} rows but found {len(rows)}")

    with REPORT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    for field in ("estimate", "cluster_se", "conventional_p"):
        maximum = max(float(row[f"abs_diff_{field}"]) for row in rows)
        print(f"{field}: maximum absolute difference = {maximum:.12g}")
    print(f"Compared {len(rows)} regressions across {cases} panels")
    print("All N, city-cluster, and treated-city counts match" if all(
        row[f"stata_{field}"] == row[f"python_{field}"]
        for row in rows
        for field in ("observations", "city_clusters", "treated_cities")
    ) else "Count mismatch detected")
    if stale:
        raise SystemExit("FAIL: source panel or Python result is newer than the Stata results; rerun the do file")
    if any(row["status"] != "PASS" for row in rows):
        raise SystemExit("FAIL: see Stata与Python逐项核对.csv")
    print("PASS: all regressions match")


if __name__ == "__main__":
    main()
