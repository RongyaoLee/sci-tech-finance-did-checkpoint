"""Recompute the common-window outcomes without holding full-year sorting indexes."""
import argparse
import csv
import gzip
import json
import re
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
EPOCH = np.datetime64("1960-01-01", "D")
LEGACY_MONTH_ORIGIN_YEAR = 2019
NBIN = 1024 * 128
LVL = {1: "小类", 2: "中类", 3: "大类"}
SCOPE = json.loads((BASE / "scope_codes.json").read_text(encoding="utf-8"))
S4 = SCOPE["four"]
S3_FULL_M = set(SCOPE["three_full_M"]) | set(SCOPE["declared3"])
S3_FULL_S = set(SCOPE["three_full_S"])
S2_FULL_M = set(SCOPE["two_full_M"]) | set(SCOPE["declared2"])
S2_FULL_S = set(SCOPE["two_full_S"])
with (BASE / "gb4754_codes.csv").open(encoding="utf-8-sig", newline="") as stream:
    GB = {row["code"]: row["sector_letter"] for row in csv.DictReader(stream)}

COUNTS = ("all_new", "manufacturing", "services", "hightech",
          "partial_candidate", "exact4", "exact_manufacturing", "exact_services")
NON_ENTERPRISE = re.compile("个体|分公司|分支|合作社|合作经济组织|社会团体|民办非企业|基金会|"
                            "事业单位|机关法人|村民委员会|居民委员会|代表处|办事处|营业部|非法人|经营单位")
ENTERPRISE = re.compile("公司|企业|个人独资|合伙|全民所有制|集体所有制|股份合作制|联营|私营独资")


def dec(raw):
    value = bytes(raw).split(b"\0", 1)[0].strip()
    return value.decode("utf-8", errors="replace")


def industry_code(raw, digits):
    value = dec(raw)
    if len(value) == digits and value in GB:
        return value
    if len(value) == digits + 1 and GB.get(value[1:]) == value[0]:
        return value[1:]
    return ""


def is_enterprise(raw):
    value = dec(raw)
    return bool(ENTERPRISE.search(value) and not NON_ENTERPRISE.search(value))


def classify_small(raw):
    small = industry_code(raw, 4)
    entry = S4.get(small)
    if entry:
        return 3 if entry["star"] else 1 if entry["cat"] == "M" else 2
    return 0 if small else -1


def classify_parent(raw, digits, manufacturing, services):
    key = industry_code(raw, digits)
    if key in manufacturing:
        return 1
    if key in services:
        return 2
    return 0 if key else -1


def classify_column(column, classify):
    values, index = np.unique(column, return_inverse=True)
    return np.array([classify(v) for v in values])[index]


def as_stata_date(date):
    return int((np.datetime64(date, "D") - EPOCH).astype(np.int64))


def run(year, last_month, cache, out, city_patch=None, dedup_mode="exclude-embedded-nul"):
    meta = json.loads((cache / f"{year}.json").read_text(encoding="utf-8"))
    rows = np.memmap(cache / f"{year}.bin", mode="r", dtype=[tuple(x) for x in meta["dtype"]])
    if len(rows) != meta["rows"]:
        raise ValueError("缓存记录数不符")
    if city_patch is not None:
        patch = np.memmap(city_patch, mode="r",
                          dtype=[("row_index", "<u4"), ("city_code", "S6")])
        patch_indices = np.ascontiguousarray(patch["row_index"])
        if patch_indices[-1] >= len(rows) or not np.all(patch_indices[1:] > patch_indices[:-1]):
            raise ValueError("城市补码行号越界或非严格递增")
    else:
        patch = patch_indices = None
    start = as_stata_date(f"{year}-01-01")
    # Cell files contain one year each.  Keep the historical 2019-origin slots
    # for 2019+ caches; give earlier years their own 1-based monthly slots.
    month_origin_year = min(year, LEGACY_MONTH_ORIGIN_YEAR)
    month0 = np.datetime64(f"{month_origin_year}-01", "M")
    boundary = as_stata_date(f"{year + 1}-01-01" if last_month == 12
                             else f"{year}-{last_month + 1:02}-01")
    founded = np.ascontiguousarray(rows["founded"])
    within = np.flatnonzero((start <= founded) & (founded < boundary))
    print(f"[{year}] {len(within):,} rows in months 1–{last_month}", flush=True)
    keys = rows["credit_code"][within]
    date_order = np.lexsort((founded[within], keys))
    sorted_keys = keys[date_order]
    dup = np.r_[False, sorted_keys[1:] == sorted_keys[:-1]]
    dup &= np.char.strip(sorted_keys) != b""
    if dedup_mode == "exclude-embedded-nul":
        # Some records contain a repeated placeholder with a NUL followed by
        # nonzero bytes.  Normal Stata string padding has only trailing NULs.
        credit_bytes = sorted_keys.view(np.uint8).reshape(len(sorted_keys), sorted_keys.dtype.itemsize)
        embedded_nul = np.any((credit_bytes[:, :-1] == 0) &
                              (credit_bytes[:, 1:] != 0), axis=1)
        dup &= ~embedded_nul
        del credit_bytes, embedded_nul
    elif dedup_mode != "legacy":
        raise ValueError(f"未知去重模式: {dedup_mode}")
    unique_pos = np.sort(within[date_order[~dup]])
    audit = dict(raw_rows=len(rows), window_rows=len(within), dropped_dup=int(dup.sum()),
                 dropped_entity=0, missing_industry=0, missing_city=0, ht_manu=0, ht_serv=0,
                 ht_total=0, ht_exact4=0, ht_star_candidate=0, lvl_xiaolei=0,
                 lvl_zhonglei=0, lvl_dalei=0, distinct_cities=0)
    del keys, date_order, sorted_keys, dup, within

    cities = {}
    acc = np.zeros((NBIN, len(COUNTS)), dtype=np.int64)
    out.mkdir(exist_ok=True, parents=True)
    with gzip.open(out / f"validated_detail_{year}.csv.gz", "wt", encoding="utf-8-sig",
                   newline="", compresslevel=1) as file:
        writer = csv.writer(file)
        writer.writerow(["record_id", "credit_code", "founded_date", "city_code", "gb_code",
                         "category", "match_level"])
        for offset in range(0, len(unique_pos), 400_000):
            ids = unique_pos[offset:offset + 400_000]
            entity = classify_column(rows["entity_type"][ids], is_enterprise)
            audit["dropped_entity"] += len(ids) - int(entity.sum())
            ids = ids[entity]
            small_raw, group_raw, major_raw = (rows[key][ids] for key in ("industry", "group", "major"))
            small = classify_column(small_raw, classify_small)
            group = classify_column(group_raw, lambda r: classify_parent(r, 3, S3_FULL_M, S3_FULL_S))
            major = classify_column(major_raw, lambda r: classify_parent(r, 2, S2_FULL_M, S2_FULL_S))
            category = np.where(small >= 0, small, np.where(group >= 0, group, major))
            level = np.where(small >= 0, 1, np.where(group >= 0, 2, 3))
            raw_city = rows["city_code"][ids]
            if patch is not None:
                positions = np.flatnonzero(np.char.strip(raw_city) == b"")
                indices = np.searchsorted(patch_indices, ids[positions])
                in_bounds = indices < len(patch_indices)
                positions, indices = positions[in_bounds], indices[in_bounds]
                matched = patch_indices[indices] == ids[positions]
                raw_city[positions[matched]] = patch["city_code"][indices[matched]]

            def city_slot(raw):
                key = dec(raw)
                return cities.setdefault(key, len(cities)) if re.fullmatch(r"[0-9]{6}", key) else -1

            slots = classify_column(raw_city, city_slot)
            has_city = slots >= 0
            dates = EPOCH + founded[ids].astype("timedelta64[D]")
            month = (dates.astype("datetime64[M]") - month0).astype(np.int64) + 1
            if month.min() < 1 or month.max() >= 128:
                raise ValueError(f"[{year}] 月份槽越界")
            inscope, is_m, is_s = (category == 1) | (category == 2), category == 1, category == 2
            exact_m, exact_s = is_m & (level == 1), is_s & (level == 1)
            flags = (np.ones(len(ids), dtype=bool), is_m, is_s, inscope, category == 3,
                     exact_m | exact_s, exact_m, exact_s)
            bins = slots[has_city] * 128 + month[has_city]
            for col, mask in enumerate(flags):
                acc[:, col] += np.bincount(bins[mask[has_city]], minlength=NBIN)
            audit["missing_city"] += int((~has_city).sum())
            audit["missing_industry"] += int((category == -1).sum())
            for key, mask in zip(("ht_manu", "ht_serv", "ht_total", "ht_star_candidate",
                                  "ht_exact4"), flags[1:6]):
                audit[key] += int(mask.sum())
            for i, key in enumerate(("lvl_xiaolei", "lvl_zhonglei", "lvl_dalei"), start=1):
                audit[key] += int((inscope & (level == i)).sum())
            sub = np.flatnonzero(inscope)
            records = rows["record_id"][ids[sub]]
            codes = rows["credit_code"][ids[sub]]
            raw_by_level = (small_raw, group_raw, major_raw)
            writer.writerows(
                (dec(record), dec(credit), str(dates[pos]), dec(raw_city[pos]),
                 industry_code(raw_by_level[level[pos] - 1][pos], int(5 - level[pos])),
                 "制造业" if is_m[pos] else "服务业", LVL[level[pos]])
                for pos, record, credit in zip(sub, records, codes)
            )
            if offset % 2_000_000 == 0:
                print(f"[{year}] {offset + len(entity):,}/{len(unique_pos):,}", flush=True)
    audit.update(distinct_cities=len(cities), month_index_origin_year=month_origin_year,
                 date_min=f"{year}-01-01",
                 date_max=str(EPOCH + np.timedelta64(boundary - 1, "D")))
    if dedup_mode != "legacy":
        audit["dedup_mode"] = dedup_mode
    assert audit["ht_total"] == audit["ht_manu"] + audit["ht_serv"] == sum(
        audit[key] for key in ("lvl_xiaolei", "lvl_zhonglei", "lvl_dalei"))
    np.savez_compressed(out / f"validated_{year}_cells.npz", acc=acc, cities=np.array(list(cities)))
    (out / f"validated_{year}_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{year}] DONE {audit}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("years", nargs="+", type=int)
    parser.add_argument("--last-month", type=int, choices=range(1, 13), default=5)
    parser.add_argument("--cache", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, default=BASE / "window")
    parser.add_argument("--city-patch-2023", type=Path)
    parser.add_argument("--dedup-mode", choices=("legacy", "exclude-embedded-nul"),
                        default="exclude-embedded-nul")
    args = parser.parse_args()
    for year in args.years:
        run(year, args.last_month, args.cache, args.output,
            args.city_patch_2023 if year == 2023 else None, args.dedup_mode)
