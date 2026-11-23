"""Conservative sensitivity patch for 2023 city-code missingness.

For each exact original province/city spelling, use only an overwhelmingly
dominant *observed* six-digit code: >=100 same-source anchors, >=98% share,
province prefix matches its dominant anchored province prefix, and the code's
dominant standardized province/city names match the original names exactly.
Excluded pairs and all anomalous codes remain in the audit CSV.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
RAW_DTYPE = np.dtype([('row_index', '<u4'), ('raw_province', 'S24'), ('raw_city', 'S33')])
PATCH_DTYPE = np.dtype([('row_index', '<u4'), ('city_code', 'S6')])


def clean(x):
    return bytes(x).strip(b'\0 ')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=BASE)
    parser.add_argument('--geography', type=Path)
    options = parser.parse_args()
    directory = options.geography or options.cache / 'geography_2023'
    anchors = defaultdict(dict)
    with (directory/'city_anchors.csv').open(encoding='utf-8-sig', newline='') as file:
        for row in list(csv.reader(file))[1:]:
            anchors[(row[0].encode(), row[1].encode())][row[2].encode()] = int(row[3])

    province_prefix = defaultdict(Counter)
    for (province, _city), codes in anchors.items():
        for code, count in codes.items():
            province_prefix[province][code[:2]] += count
    province_dominant = {}
    for province, counts in province_prefix.items():
        prefix, n = counts.most_common(1)[0]
        province_dominant[province] = (prefix, n/sum(counts.values()))

    meta = json.loads((options.cache/'2023.json').read_text(encoding='utf8'))
    cache = np.memmap(options.cache/'2023.bin',
                      dtype=np.dtype([tuple(x) for x in meta['dtype']]), mode='r')
    name_counts = Counter()
    block_rows = 65536
    for start in range(0, len(cache), block_rows):
        x = cache[start:start+block_rows]
        codes = np.char.strip(x['city_code'])
        ok = np.char.isdigit(codes) & (np.char.str_len(codes) == 6)
        if not ok.any():
            continue
        triple = np.empty(int(ok.sum()), dtype=[('code', 'S6'), ('p', 'S24'), ('c', 'S33')])
        triple['code'] = codes[ok]
        triple['p'] = np.char.strip(x['province'][ok])
        triple['c'] = np.char.strip(x['city'][ok])
        unique, counts = np.unique(triple, return_counts=True)
        for item, n in zip(unique, counts):
            name_counts[(clean(item['code']), clean(item['p']), clean(item['c']))] += int(n)
    by_code = defaultdict(Counter)
    for (code, province, city), n in name_counts.items():
        by_code[code][(province, city)] += n
    code_names = {}
    for code, counts in by_code.items():
        pair, n = counts.most_common(1)[0]
        code_names[code] = (pair, n, n/sum(counts.values()))

    accepted = {}
    decisions = []
    for (province, city), codes in sorted(anchors.items()):
        code, n = max(codes.items(), key=lambda kv: kv[1])
        total = sum(codes.values())
        share = n/total
        pfx, pfx_share = province_dominant[province]
        std_pair, std_n, std_share = code_names.get(code, ((b'', b''), 0, 0))
        reasons = []
        if n < 100:
            reasons.append('锚点不足100')
        if share < .98:
            reasons.append('首码占比低于98%')
        if code[:2] != pfx or pfx_share < .98:
            reasons.append('省级前缀不一致或证据不足')
        if std_pair != (province, city) or std_n < 100 or std_share < .98:
            reasons.append('标准省市名称未精确对应')
        if not reasons:
            accepted[(province, city)] = code
        decisions.append((province, city, code, n, total, share, len(codes),
                          pfx, pfx_share, std_pair, std_n, std_share,
                          '纳入' if not reasons else '排除：'+'；'.join(reasons)))

    with (directory/'conservative_city_decisions.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['原省份', '原城市', '最常见明码', '该码锚点', '全部锚点', '首码占比',
                         '观察到的代码种数', '该省主前缀', '主前缀占比',
                         '该码标准化省份', '该码标准化城市', '标准名锚点', '标准名占比', '决定'])
        for p, c, code, n, total, share, n_codes, pfx, pfx_share, std_pair, std_n, std_share, decision in decisions:
            writer.writerow([p.decode('utf8', 'replace'), c.decode('utf8', 'replace'), code.decode(),
                             n, total, share, n_codes, pfx.decode(), pfx_share,
                             std_pair[0].decode('utf8', 'replace'), std_pair[1].decode('utf8', 'replace'),
                             std_n, std_share, decision])

    recovered = 0
    unresolved = 0
    patch_part = directory/'conservative_city_patch.bin.part'
    with (directory/'missing_city_raw.bin').open('rb') as source, patch_part.open('wb') as target:
        while True:
            chunk = np.fromfile(source, dtype=RAW_DTYPE, count=65536)
            if not len(chunk):
                break
            pairs, inverse = np.unique(chunk[['raw_province', 'raw_city']], return_inverse=True)
            values = np.array([accepted.get((clean(p['raw_province']), clean(p['raw_city'])), b'')
                               for p in pairs], dtype='S6')
            codes = values[inverse]
            ok = codes != b''
            patch = np.empty(int(ok.sum()), dtype=PATCH_DTYPE)
            patch['row_index'] = chunk['row_index'][ok]
            patch['city_code'] = codes[ok]
            patch.tofile(target)
            recovered += int(ok.sum())
            unresolved += int((~ok).sum())
    patch_part.replace(directory/'conservative_city_patch.bin')
    previous = json.loads((directory/'audit.json').read_text(encoding='utf8'))
    audit = {'source_zip_crc32': previous['source_crc32'],
             'missing_standard_city_code': previous['missing_standard_city_code'],
             'accepted_original_province_city_pairs': len(accepted),
             'excluded_original_province_city_pairs': len(anchors)-len(accepted),
             'recovered_rows': recovered, 'unresolved_rows': unresolved,
             'rule': 'Exact original province+city spelling; modal observed code >=100 anchors and >=98% of all anchors; code province prefix agrees with dominant prefix for province (>=98%); dominant standardized province+city names equal original names exactly (>=100 anchors, >=98%).',
             'patch_dtype': PATCH_DTYPE.descr}
    assert recovered+unresolved == previous['missing_standard_city_code']
    (directory/'conservative_audit.json').write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(audit, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
