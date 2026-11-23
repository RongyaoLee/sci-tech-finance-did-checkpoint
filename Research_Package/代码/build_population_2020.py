"""Build the 2020 fixed city population denominator from Dong et al.'s census CSV.

Usage:
    python build_population_2020.py [path/to/census_city_2010-2020_v1.csv] [output.csv]

If the source path is omitted, download the original public CSV. The output
defaults to ../population_2020.csv relative to this script.
"""

import csv
import hashlib
import io
import pathlib
import sys
import urllib.request

SOURCE_URL = (
    "https://raw.githubusercontent.com/jaehyunhan/chinapopulation/main/"
    "data/census/census_city_2010-2020_v1.csv"
)
SOURCE_SHA256 = "CEF8BA063A7CDA6F6EED99CD71CFA18AEED2EF09BC517A514810DF874E99913A"

# The source uses prefectural codes for municipalities; the business register
# uses province-level codes for these four same administrative units.
MUNICIPALITY_CODES = {
    "110100": "110000",  # Beijing
    "120100": "120000",  # Tianjin
    "310100": "310000",  # Shanghai
    "500100": "500000",  # Chongqing
}

# City-level source rows omit separately counted areas that register under
# their parent city code in the business file. Each replacement is an official
# seventh-census figure or sum of official seventh-census figures, in persons.
BOUNDARY_ADJUSTMENTS = {
    "130600": 11_437_217,  # Baoding incl. Dingzhou and Xiong'an, Baoding govt
    "460400": 954_259,  # Danzhou 871118 + Yangpu 83141, Hainan census
    "610400": 4_213_713,  # Xianyang 3959842 + Yangling 253871, Shaanxi census
}


def main() -> None:
    if len(sys.argv) > 3:
        raise SystemExit("usage: python build_population_2020.py [source.csv] [output.csv]")
    raw = (
        pathlib.Path(sys.argv[1]).read_bytes()
        if len(sys.argv) >= 2
        else urllib.request.urlopen(SOURCE_URL, timeout=60).read()
    )
    actual_hash = hashlib.sha256(raw).hexdigest().upper()
    if actual_hash != SOURCE_SHA256:
        raise SystemExit(f"Source CSV SHA-256 mismatch: {actual_hash}")

    records = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        code = row["city_code"]
        value = row["popu_2020"]
        if not value or code.startswith(("81", "82", "659")):
            continue  # HK/Macau and Xinjiang Corps cities without source values
        code = MUNICIPALITY_CODES.get(code, code)
        if code in records:
            raise SystemExit(f"Duplicate city code: {code}")
        records[code] = int(value)

    for code, value in BOUNDARY_ADJUSTMENTS.items():
        if code not in records:
            raise SystemExit(f"Boundary adjustment city missing: {code}")
        records[code] = value
    if len(records) != 357:
        raise SystemExit(f"Unexpected city count: {len(records)}")

    output = (
        pathlib.Path(sys.argv[2])
        if len(sys.argv) >= 3
        else pathlib.Path(__file__).resolve().parent.parent / "population_2020.csv"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["city_code", "population_2020"])
        writer.writerows(sorted(records.items()))
    print(f"Wrote {len(records)} cities to {output}; population sum {sum(records.values())}")


if __name__ == "__main__":
    main()
