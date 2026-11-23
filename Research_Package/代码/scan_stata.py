"""Stream the fixed-width records in a zipped Stata 118 file."""

import argparse
import csv
import json
import struct
from pathlib import Path
from zipfile import ZipFile

import numpy as np


FIELDS = {
    "newgcid": "record_id",
    "企业名称": "company",
    "成立日期": "founded",
    "成立年份": "year_column",
    "行业门类代码": "sector",
    "行业大类代码": "major",
    "行业中类代码": "group",
    "行业小类代码": "industry",
    "行业小类": "industry_name",
    "统一社会信用代码": "credit_code",
    "企业类型": "entity_type",
    "经营状态": "status",
    "省": "province",
    "市": "city",
    "市代码": "city_code",
    "县代码": "county_code",
}
STATA_TYPES = {65526: "<f8", 65527: "<f4", 65528: "<i4", 65529: "<i2",
               65530: "i1", 32768: "V8"}


def table_layout(stream):
    header = stream.read(32759)

    def section(tag):
        return header.split(b"<" + tag + b">", 1)[1].split(b"</" + tag + b">", 1)[0]

    if section(b"release") != b"118" or section(b"byteorder") != b"LSF":
        raise ValueError("Expected little-endian Stata format 118")
    nvars = int.from_bytes(section(b"K"), "little")
    nrows = int.from_bytes(section(b"N"), "little")
    locations = struct.unpack("<14Q", section(b"map"))
    # Keep the stream at the first byte of the data section.
    data_start = locations[9] + len(b"<data>")
    if stream.tell() != data_start or not header.endswith(b"<data>"):
        stream.seek(data_start)
    raw_names = section(b"varnames")
    raw_types = struct.unpack(f"<{nvars}H", section(b"variable_types"))
    names = [
        raw_names[i:i + 129].split(b"\0", 1)[0].decode()
        for i in range(0, nvars * 129, 129)
    ]
    fields = {}
    width = 0
    for name, stata_type in zip(names, raw_types):
        dtype = np.dtype(STATA_TYPES.get(stata_type, f"S{stata_type}"))
        if name in FIELDS:
            fields[FIELDS[name]] = (dtype, width)
        width += dtype.itemsize
    if len(fields) != len(FIELDS) or width * nrows != locations[10] - data_start - len(b"</data>"):
        raise ValueError("Stata field layout and data section do not agree")
    dtype = np.dtype({"names": list(fields),
                      "formats": [d.str for d, _ in fields.values()],
                      "offsets": [o for _, o in fields.values()], "itemsize": width})
    slim = np.dtype([(k, d) for k, (d, _) in fields.items()])
    return dtype, slim, nrows, data_start


def scan(archive, prefix):
    with ZipFile(archive) as z:
        files = [entry for entry in z.infolist() if entry.filename.endswith(".dta")]
        if len(files) != 1:
            raise ValueError("Expected exactly one .dta in the archive")
        member = files[0]
        with z.open(member) as source:
            dtype, slim, nrows, start = table_layout(source)
            print(f"{archive.name}: {nrows:,} rows, {dtype.itemsize:,} bytes/row", flush=True)
            tmp = prefix.with_suffix(".bin.part")
            with tmp.open("wb") as target:
                chunk_rows = 32768
                for pos in range(0, nrows, chunk_rows):
                    size = min(chunk_rows, nrows - pos)
                    rows = np.frombuffer(source.read(size * dtype.itemsize), dtype=dtype)
                    if len(rows) != size:
                        raise ValueError(f"Truncated after {pos:,} rows")
                    compact = np.empty(size, dtype=slim)
                    for name in slim.names:
                        compact[name] = rows[name]
                    compact.tofile(target)
                    if (pos // chunk_rows) % 30 == 0:
                        print(f"{pos + size:,} / {nrows:,} rows read", flush=True)
            if source.read(7) != b"</data>":
                raise ValueError("Unexpected end of Stata data")
            # Reading to EOF verifies the zip CRC, including the unused strL section.
            while source.read(32 * 1024 * 1024):
                pass
        tmp.replace(prefix.with_suffix(".bin"))
        prefix.with_suffix(".json").write_text(json.dumps({
            "archive": str(archive), "member": member.filename, "member_bytes": member.file_size,
            "rows": nrows, "record_bytes": dtype.itemsize, "dtype": slim.descr,
            "crc32": f"{member.CRC:08x}", "data_offset": start,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Verified {nrows:,} records and zip CRC.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("prefix", type=Path)
    options = parser.parse_args()
    scan(options.archive, options.prefix)
