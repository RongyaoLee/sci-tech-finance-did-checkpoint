"""Exact-anchor recovery of missing 2023 standardized city codes.

One sequential pass over the original Stata ZIP extracts only row index and
original province/city for rows with missing standardized city code. Pairs
are mapped only when at least one other row in this same source has exactly
one observed six-digit standardized city code for that exact pair.
"""
import argparse
import csv
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

import numpy as np

BASE = Path(__file__).resolve().parent
RAW_DTYPE = np.dtype([('row_index', '<u4'), ('raw_province', 'S24'), ('raw_city', 'S33')])
PATCH_DTYPE = np.dtype([('row_index', '<u4'), ('city_code', 'S6')])


def clean(value):
    return bytes(value).strip(b'\0 ')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--meta', type=Path, default=BASE / '2023.json')
    ap.add_argument('--output', type=Path, default=BASE / 'geography_2023')
    args = ap.parse_args()
    meta = json.loads(args.meta.read_text(encoding='utf8'))
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / 'missing_city_raw.bin'
    raw_part = raw_path.with_suffix('.bin.part')
    patch_path = output / 'exact_city_patch.bin'
    patch_part = patch_path.with_suffix('.bin.part')
    anchor_counts = Counter()
    missing_count = 0
    missing_raw_both = 0
    nrows = meta['rows']

    with ZipFile(meta['archive']) as archive, archive.open(meta['member']) as source:
        header = source.read(meta['data_offset'])
        def section(tag):
            return header.split(b'<' + tag + b'>', 1)[1].split(b'</' + tag + b'>', 1)[0]
        if section(b'release') != b'118' or section(b'byteorder') != b'LSF':
            raise ValueError('Expected Stata 118 little-endian file')
        k = int.from_bytes(section(b'K'), 'little')
        names = [section(b'varnames')[i:i+129].split(b'\0', 1)[0].decode()
                 for i in range(0, k*129, 129)]
        types = struct.unpack(f'<{k}H', section(b'variable_types'))
        special = {65526: 8, 65527: 4, 65528: 4, 65529: 2, 65530: 1, 32768: 8}
        needed = {'省份', '城市', '市代码'}
        locations = {}
        offset = 0
        for name, typ in zip(names, types):
            width = special.get(typ, typ)
            if name in needed:
                locations[name] = (offset, width)
            offset += width
        if set(locations) != needed or offset != meta['record_bytes']:
            raise ValueError('Stata field layout differs from cached metadata')
        dtype = np.dtype({'names': ['raw_province', 'raw_city', 'city_code'],
                          'formats': [f'S{locations[name][1]}' for name in ('省份', '城市', '市代码')],
                          'offsets': [locations[name][0] for name in ('省份', '城市', '市代码')],
                          'itemsize': offset})
        with raw_part.open('wb') as target:
            block_rows = 32768
            for start in range(0, nrows, block_rows):
                size = min(block_rows, nrows-start)
                content = source.read(size*offset)
                if len(content) != size*offset:
                    raise ValueError(f'Truncated at row {start}')
                records = np.frombuffer(content, dtype=dtype)
                code = np.char.strip(records['city_code'])
                code_valid = np.char.isdigit(code) & (np.char.str_len(code) == 6)
                province = np.char.strip(records['raw_province'])
                city = np.char.strip(records['raw_city'])
                raw_both = (province != b'') & (city != b'')
                anchor = code_valid & raw_both
                if anchor.any():
                    triples = np.empty(int(anchor.sum()), dtype=[('p', 'S24'), ('c', 'S33'), ('z', 'S6')])
                    triples['p'] = province[anchor]
                    triples['c'] = city[anchor]
                    triples['z'] = code[anchor]
                    unique, counts = np.unique(triples, return_counts=True)
                    for item, count in zip(unique, counts):
                        anchor_counts[(clean(item['p']), clean(item['c']), clean(item['z']))] += int(count)
                missing = ~code_valid
                missing_count += int(missing.sum())
                missing_raw_both += int((missing & raw_both).sum())
                if missing.any():
                    slim = np.empty(int(missing.sum()), dtype=RAW_DTYPE)
                    slim['row_index'] = np.arange(start, start+size, dtype=np.uint32)[missing]
                    slim['raw_province'] = province[missing]
                    slim['raw_city'] = city[missing]
                    slim.tofile(target)
                if start % (block_rows*32) == 0:
                    print(f'scanned={start+size:,}/{nrows:,} missing={missing_count:,} anchors={len(anchor_counts):,}', flush=True)
            if source.read(7) != b'</data>':
                raise ValueError('Unexpected Stata data ending')
            while source.read(32*1024*1024):
                pass
    raw_part.replace(raw_path)

    by_pair = defaultdict(dict)
    for (province, city, code), count in anchor_counts.items():
        by_pair[(province, city)][code] = count
    exact = {pair: next(iter(codes)) for pair, codes in by_pair.items() if len(codes) == 1}
    ambiguous = {pair for pair, codes in by_pair.items() if len(codes) > 1}
    anchors_csv = output / 'city_anchors.csv'
    with anchors_csv.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['原省份', '原城市', '标准化城市码', '明码锚点条数', '该原省市对应代码数', '状态'])
        for (province, city), codes in sorted(by_pair.items()):
            for code, count in sorted(codes.items()):
                writer.writerow([province.decode('utf8', 'replace'), city.decode('utf8', 'replace'),
                                 code.decode(), count, len(codes), '唯一' if len(codes) == 1 else '冲突不补'])
    recovered = 0
    raw_blank = 0
    ambiguous_rows = 0
    unanchored = 0
    with raw_path.open('rb') as source, patch_part.open('wb') as target:
        while True:
            chunk = np.fromfile(source, dtype=RAW_DTYPE, count=65536)
            if not len(chunk):
                break
            pairs, inverse = np.unique(chunk[['raw_province', 'raw_city']], return_inverse=True)
            values = np.empty(len(pairs), dtype='S6')
            values[:] = b''
            for j, pair in enumerate(pairs):
                key = clean(pair['raw_province']), clean(pair['raw_city'])
                if not key[0] or not key[1]:
                    raw_blank += int((inverse == j).sum())
                elif key in ambiguous:
                    ambiguous_rows += int((inverse == j).sum())
                elif key in exact:
                    values[j] = exact[key]
                else:
                    unanchored += int((inverse == j).sum())
            codes = values[inverse]
            ok = codes != b''
            patch = np.empty(int(ok.sum()), dtype=PATCH_DTYPE)
            patch['row_index'] = chunk['row_index'][ok]
            patch['city_code'] = codes[ok]
            patch.tofile(target)
            recovered += int(ok.sum())
    patch_part.replace(patch_path)
    audit = {'source_zip': meta['archive'], 'source_member': meta['member'],
             'source_crc32': meta['crc32'], 'source_rows': nrows,
             'raw_dtype': RAW_DTYPE.descr, 'patch_dtype': PATCH_DTYPE.descr,
             'missing_standard_city_code': missing_count,
             'missing_with_raw_province_and_city': missing_raw_both,
             'exact_anchor_pairs': len(exact), 'ambiguous_anchor_pairs': len(ambiguous),
             'recovered_by_exact_anchor': recovered, 'unresolved_raw_blank': raw_blank,
             'unresolved_ambiguous': ambiguous_rows, 'unresolved_unanchored': unanchored,
             'rule': 'Same-source exact raw province+city pair, one and only one observed six-digit city code; no fuzzy inference.'}
    assert recovered+raw_blank+ambiguous_rows+unanchored == missing_count
    (output/'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(audit, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
