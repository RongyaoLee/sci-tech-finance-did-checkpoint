"""Exact month-level coverage counters for one year (full scan, vectorised).

Writes work/registration/coverage_<year>.json with, per calendar month:
  rows, city_ok, ind4_ok, both_ok, and the max/min dates seen with city_ok True/False.
"""
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
EPOCH = np.datetime64("1960-01-01", "D")
MONTH0 = np.datetime64("2000-01", "M")
NC = 480


def main(year: int):
    meta = json.loads((BASE / f"{year}.json").read_text(encoding="utf-8"))
    dtype = np.dtype([tuple(x) for x in meta["dtype"]])
    rows = np.memmap(BASE / f"{year}.bin", mode="r", dtype=dtype)
    n = rows.shape[0]

    city_ok = np.zeros(NC, dtype=np.int64)
    ind4_ok = np.zeros(NC, dtype=np.int64)
    both_ok = np.zeros(NC, dtype=np.int64)
    tot = np.zeros(NC, dtype=np.int64)

    dmax_city, dmin_nocity = None, None
    CH = 2_000_000
    for start in range(0, n, CH):
        stop = min(start + CH, n)
        sl = rows[start:stop]
        f = np.asarray(sl["founded"]).astype(np.int64)
        dates = EPOCH + f.astype("timedelta64[D]")
        mi = ((dates.astype("datetime64[M]") - MONTH0).astype(np.int64))
        okd = (f > 0) & (mi >= 0) & (mi < NC)
        cc = np.asarray(sl["city_code"])
        ind = np.asarray(sl["industry"])
        coc = np.char.str_len(np.char.strip(cc, b"\x00")) == 6
        ioc = np.char.str_len(np.char.strip(ind, b"\x00")) == 5
        idx = mi[okd]
        tot += np.bincount(idx, minlength=NC)
        city_ok += np.bincount(idx[coc[okd]], minlength=NC)
        ind4_ok += np.bincount(idx[ioc[okd]], minlength=NC)
        both_ok += np.bincount(idx[coc[okd] & ioc[okd]], minlength=NC)
        if coc.any():
            m = dates[coc].max()
            dmax_city = m if dmax_city is None else max(dmax_city, m)
        if (~coc).any():
            m = dates[~coc].min()
            dmin_nocity = m if dmin_nocity is None else min(dmin_nocity, m)
        print(f"[{year}] {stop:,}/{n:,}", flush=True)

    out = {"year": year, "rows": int(n),
           "month_rows": tot.tolist(), "month_city_ok": city_ok.tolist(),
           "month_ind4_ok": ind4_ok.tolist(), "month_both_ok": both_ok.tolist(),
           "max_date_with_city": str(dmax_city)[:10] if dmax_city is not None else "",
           "min_date_without_city": str(dmin_nocity)[:10] if dmin_nocity is not None else ""}
    (BASE / f"coverage_{year}.json").write_text(json.dumps(out, ensure_ascii=False),
                                                encoding="utf-8")
    ys = 2000
    print(f"[{year}] month rows city_ok ind4_ok both")
    for i in range(NC):
        if tot[i]:
            y, m = ys + i // 12, i % 12 + 1
            print(f"  {y}-{m:02d} {tot[i]:9d} {city_ok[i]:9d} {ind4_ok[i]:9d} {both_ok[i]:9d}")
    print(f"[{year}] max date with city {out['max_date_with_city']}, "
          f"min date without city {out['min_date_without_city']}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
