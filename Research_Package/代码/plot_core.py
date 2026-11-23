"""Draw research-package coverage and cohort point-estimate figures with Pillow.

Run after package_tables.py and 科创金融_企业进入估计.py have written their CSVs:
    python work/registration/plot_core.py
or:
    python work/registration/plot_core.py --data-dir path/to/结果与图表

The charts use raw coverage fields exactly as recorded. They do not add
confidence intervals or statistical-significance marks to cohort estimates.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def locate_data_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == "Research_Package" and (parent / "结果与图表").is_dir():
            return parent / "结果与图表"
        candidate = parent / "outputs" / "Research_Package" / "结果与图表"
        if candidate.is_dir():
            return candidate
    raise RuntimeError("未找到 Research_Package/结果与图表；可用 --data-dir 显式指定")


WIDTH, HEIGHT = 1800, 1050
BG = "#FFFFFF"
INK = "#1A2B3C"
MUTED = "#607386"
GRID = "#DEE6EC"
BLUE = "#2465A6"
TEAL = "#0D7C86"
ORANGE = "#D76B38"
LIGHT_BLUE = "#EAF2F8"
FONT_FILE = Path(r"C:\Windows\Fonts\msyh.ttc")
BOLD_FONT_FILE = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    file = BOLD_FONT_FILE if bold and BOLD_FONT_FILE.exists() else FONT_FILE
    if not file.exists():
        raise FileNotFoundError("缺少微软雅黑字体：C:\\Windows\\Fonts\\msyh.ttc")
    return ImageFont.truetype(str(file), size)


F_TITLE = font(49, bold=True)
F_SUB = font(31)
F_AXIS = font(28)
F_LABEL = font(34)
F_VALUE = font(31, bold=True)
F_NOTE = font(27)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"尚未生成输入表：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        result = list(csv.DictReader(fh))
    if not result:
        raise ValueError(f"输入表没有数据：{path}")
    return result


def as_int(record: dict[str, str], key: str) -> int:
    value = int(record[key])
    if value < 0:
        raise ValueError(f"{key} 出现负数：{record}")
    return value


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", dpi=(300, 300), optimize=True)
    if image.size != (WIDTH, HEIGHT) or path.stat().st_size < 10_000:
        raise RuntimeError(f"图像保存异常：{path}")


def canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(im)
    draw.text((115, 72), title, fill=INK, font=F_TITLE)
    draw.text((117, 148), subtitle, fill=MUTED, font=F_SUB)
    draw.line((115, 211, WIDTH - 115, 211), fill=GRID, width=2)
    return im, draw


def center_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], value: str,
                use_font: ImageFont.FreeTypeFont, fill: str = INK) -> None:
    box = draw.textbbox((0, 0), value, font=use_font)
    draw.text((xy[0] - (box[2] - box[0]) / 2,
               xy[1] - (box[3] - box[1]) / 2 - box[1]), value, font=use_font, fill=fill)


def monthly_coverage(rows: list[dict[str, str]]) -> dict[tuple[int, int], dict[str, int]]:
    result: dict[tuple[int, int], dict[str, int]] = {}
    for row in rows:
        year, month = as_int(row, "year"), as_int(row, "month")
        if month not in range(1, 13):
            raise ValueError(f"月份无效：{row}")
        key = (year, month)
        if key in result:
            raise ValueError(f"原始记录月度覆盖重复年月：{key}")
        total = as_int(row, "source_rows")
        city = as_int(row, "raw_city_code_present")
        industry = as_int(row, "raw_industry_code_length5")
        if total == 0 or city > total or industry > total:
            raise ValueError(f"覆盖表计数不一致：{row}")
        result[key] = {"total": total, "city": city, "industry": industry}
    return result


def audit_pilots(rows: list[dict[str, str]]) -> str:
    seen: set[tuple[str, int]] = set()
    for row in rows:
        key = (row["city_code"].strip(), as_int(row, "year"))
        if key in seen:
            raise ValueError(f"七个试点城市同期统计重复城市年：{key}")
        seen.add(key)
        n_months = as_int(row, "months")
        total, manu, service, high = (as_int(row, x) for x in
                                      ("all_new", "manufacturing", "services", "hightech"))
        if n_months != 5 or high != manu + service or high > total:
            raise ValueError(f"七个试点城市同期统计计数不一致：{row}")
    return f"已核对试点城市同期汇总：{len(seen)} 个城市—年度单元，每单元均覆盖1—5月。"


def chart_industry(coverage: dict[tuple[int, int], dict[str, int]], out: Path) -> None:
    summary = []
    for year in sorted({year for year, month in coverage}):
        missing = [m for m in range(1, 6) if (year, m) not in coverage]
        if missing:
            raise ValueError(f"{year}年缺少1—5月原始覆盖记录：{missing}")
        total = sum(coverage[year, m]["total"] for m in range(1, 6))
        industry = sum(coverage[year, m]["industry"] for m in range(1, 6))
        summary.append((year, industry / total, industry, total))

    im, d = canvas(f"{summary[0][0]}—{summary[-1][0]}年同期行业四位码字段覆盖",
                   "每年1—5月原始登记记录；门类字母+四位行业小类字段长度完整的比例")
    left, right, top, step = 335, 1395, 250, min(108, 490 // max(1, len(summary)-1))
    for tick in range(0, 101, 25):
        x = left + (right - left) * tick / 100
        d.line((x, top - 25, x, top + (len(summary) - 1) * step + 87), fill=GRID, width=2)
        center_text(d, (x, 846), f"{tick}%", F_AXIS, MUTED)
    for i, (year, ratio, count, total) in enumerate(summary):
        y = top + i * step
        d.text((165, y + 23), str(year), fill=INK, font=F_LABEL)
        x2 = round(left + (right - left) * ratio)
        d.rounded_rectangle((left, y, right, y + 76), radius=17, fill=LIGHT_BLUE)
        if x2 > left:
            d.rounded_rectangle((left, y, max(left + 8, x2), y + 76), radius=17,
                                fill=TEAL if year == 2023 else BLUE)
        d.text((1470, y + 3), f"{ratio:.1%}", fill=INK, font=F_VALUE)
        d.text((1470, y + 45), f"{count:,}/{total:,}", fill=MUTED, font=F_NOTE)
    d.text((115, 925), "说明：字段覆盖按原始记录汇总；完整度依据代码长度，未替代行业类别有效性核对。",
           fill=MUTED, font=F_NOTE)
    save_png(im, out)


def chart_geography(coverage: dict[tuple[int, int], dict[str, int]], out: Path) -> None:
    data = [coverage.get((2023, month)) for month in range(1, 13)]
    if not any(item is not None for item in data):
        raise ValueError("原始覆盖表没有2023年月度记录")
    im, d = canvas("2023年各月六位城市代码字段覆盖",
                   "原始登记记录中城市代码长度为六位的比例；蓝色为1—5月同期分析窗口")
    left, right, top, bottom = 180, 1660, 268, 795
    for tick in range(0, 101, 20):
        y = bottom - (bottom - top) * tick / 100
        d.line((left, y, right, y), fill=GRID, width=2)
        d.text((88, y - 16), f"{tick}%", fill=MUTED, font=F_AXIS)
    spacing = (right - left) / 12
    bar_w = 74
    for month, item in enumerate(data, start=1):
        x = left + spacing * (month - .5)
        color = BLUE if month <= 5 else ORANGE
        if item:
            pct = item["city"] / item["total"]
            y = bottom - (bottom - top) * pct
            if pct:
                d.rounded_rectangle((x - bar_w / 2, y, x + bar_w / 2, bottom),
                                    radius=7, fill=color)
            label_y = min(bottom - 32, max(top - 32, y - 32))
            center_text(d, (x, label_y), f"{pct:.0%}", F_AXIS, INK)
        else:
            center_text(d, (x, bottom - 27), "—", F_AXIS, MUTED)
        center_text(d, (x, 844), f"{month}月", F_AXIS, INK)
    d.text((115, 925), "说明：分母为当月原始记录数；“—”表示该月无可用原始记录，并非覆盖率为零。",
           fill=MUTED, font=F_NOTE)
    save_png(im, out)


def nice_bound(max_abs: float) -> float:
    if max_abs <= 0:
        return 1.0
    raw = max_abs * 1.28
    power = 10 ** math.floor(math.log10(raw))
    for multiplier in (1, 2, 2.5, 5, 10):
        bound = multiplier * power
        if bound >= raw:
            return bound
    return 10 * power


def chart_cohorts(rows: list[dict[str, str]], out: Path) -> None:
    subset = []
    seen = set()
    for row in rows:
        if row["outcome"] != "hightech_per_10k" or row["comparison"] != "post_policy":
            continue
        cohort, year = as_int(row, "cohort_year"), as_int(row, "year")
        key = (cohort, year)
        if key in seen:
            raise ValueError(f"分批同期差分出现重复主密度估计：{key}")
        seen.add(key)
        est = float(row["estimate"])
        if not math.isfinite(est):
            raise ValueError(f"分批同期差分估计非有限数值：{row}")
        subset.append((cohort, year, est, as_int(row, "treated_cities"),
                       as_int(row, "comparison_cities")))
    if not subset:
        raise ValueError("分批同期差分表中没有主密度的政策后点估计")
    subset.sort(key=lambda r: (r[0], r[1]))
    if len(subset) > 5:
        raise ValueError("主密度分批点估计超出预期五行，需人工核查绘图布局")
    max_abs = max(abs(row[2]) for row in subset)
    bound = nice_bound(max_abs)
    left, right = 615, 1520
    zero = (left + right) / 2
    half = (right - left) / 2
    im, d = canvas("分批同期差分：高技术产业企业设立密度",
                   "政策后点估计；单位为每万名2020年常住人口对应的新设企业家数")
    d.text((115, 226), "仅展示点估计；未计算置信区间", fill=ORANGE, font=F_NOTE)
    if len(subset) <= 3:
        first_y, step = 370, 155
    elif len(subset) == 4:
        first_y, step = 330, 130
    else:
        first_y, step = 315, 105
    bottom = first_y + (len(subset) - 1) * step + 74
    for i, tick in enumerate((-bound, -bound / 2, 0, bound / 2, bound)):
        x = left + (right - left) * i / 4
        d.line((x, first_y - 45, x, bottom), fill=MUTED if tick == 0 else GRID,
               width=4 if tick == 0 else 2)
        center_text(d, (x, bottom + 48), f"{tick:.2f}", F_AXIS, MUTED)
    for i, (cohort, year, est, treated, controls) in enumerate(subset):
        y = first_y + i * step
        name = "济南批次" if cohort == 2022 else "长三角五市批次" if cohort == 2023 else f"{cohort}年批次"
        d.text((115, y - 33), f"{name} · {year}年", fill=INK, font=F_LABEL)
        d.text((115, y + 11), f"处理{treated}市；对照{controls}市", fill=MUTED, font=F_NOTE)
        x = zero + est / bound * half
        color = BLUE if cohort == 2022 else TEAL
        d.line((zero, y, x, y), fill=color, width=5)
        if cohort == 2022:
            d.ellipse((x - 12, y - 12, x + 12, y + 12), fill=color, outline=BG, width=2)
        else:
            d.polygon(((x, y - 15), (x + 15, y), (x, y + 15), (x - 15, y)), fill=color)
        d.text((1560, y - 24), f"{est:+.3f}", fill=INK, font=F_VALUE)
    d.text((115, 924), "说明：各批与始终未试点城市比较；图中未绘制显著性符号或误差线。",
           fill=MUTED, font=F_NOTE)
    save_png(im, out)


def chart_shares(data: Path, out: Path) -> None:
    from scipy.stats import t

    inputs = [(2020, data), (2019, data / "延长政策前样本"),
              (2018, data / "2018—2023年扩展样本")]
    entries = []
    for year, directory in inputs:
        filename = directory / "主口径" / "双向固定效应.csv"
        if not filename.exists():
            continue
        row = next(r for r in read_csv(filename) if r["outcome"] == "hightech_share")
        estimate = 100 * float(row["estimate"])
        margin = 100 * float(row["cluster_se"]) * t.ppf(.975, int(row["city_clusters"]) - 1)
        entries.append((year, estimate, estimate - margin, estimate + margin))
    lower = math.floor(min(0, *(r[2] for r in entries)))
    upper = math.ceil(max(0, *(r[3] for r in entries)))
    im, d = canvas("试点城市新设企业中高技术产业占比的相对变化",
                   "点为估计值，横线为按城市聚类的常规95%置信区间。单位为百分点。")
    left, right, top, step = 540, 1520, 310, 92
    bottom = top + step * (len(entries) - 1) + 60

    def xpos(value):
        return left + (value - lower) * (right - left) / (upper - lower)

    for tick in range(lower, upper + 1):
        x = xpos(tick)
        d.line((x, top - 45, x, bottom), fill=MUTED if tick == 0 else GRID,
               width=4 if tick == 0 else 2)
        center_text(d, (x, bottom + 38), str(tick), F_AXIS, MUTED)
    for i, (year, value, lo, hi) in enumerate(entries):
        y = top + i * step
        color = BLUE
        d.text((110, y - 20), f"{year}—2023年", fill=INK, font=F_SUB)
        d.line((xpos(lo), y, xpos(hi), y), fill=color, width=6)
        for limit in (lo, hi):
            d.line((xpos(limit), y - 10, xpos(limit), y + 10), fill=color, width=4)
        x = xpos(value)
        d.ellipse((x-11, y-11, x+11, y+11), fill=color)
        d.text((1570, y - 21), f"{value:+.2f}", fill=INK, font=F_VALUE)
    d.text((115, 925), "各年统一取1—5月；占比的分母为同城同期全部新设企业。",
           fill=MUTED, font=F_NOTE)
    save_png(im, out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path)
    args = ap.parse_args()
    data = (args.data_dir or locate_data_dir()).resolve()
    coverage = monthly_coverage(read_csv(data / "原始记录月度覆盖.csv"))
    pilot_note = audit_pilots(read_csv(data / "七个试点城市同期统计.csv"))
    cohort_file = data / "主口径" / "分批同期差分.csv"
    if not cohort_file.is_file():
        cohort_file = data / "分批同期差分.csv"
    cohorts = read_csv(cohort_file)
    output = [data / "图1_同期行业四位码字段覆盖.png",
              data / "图2_2023年月度城市代码覆盖.png",
              data / "图3_分批主密度点估计_无置信区间.png"]
    extended = data / "延长政策前样本" / "原始记录月度覆盖.csv"
    six_years = data / "2018—2023年扩展样本" / "原始记录月度覆盖.csv"
    first_coverage = six_years if six_years.is_file() else extended
    chart_industry(monthly_coverage(read_csv(first_coverage)) if first_coverage.is_file() else coverage, output[0])
    chart_geography(coverage, output[1])
    chart_cohorts(cohorts, output[2])
    output.append(data / "图4_新设企业中高技术产业占比.png")
    chart_shares(data, output[-1])
    print(pilot_note)
    for path in output:
        print(f"绘制完成：{path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
