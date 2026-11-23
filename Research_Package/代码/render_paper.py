from pathlib import Path
import argparse
import re
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("target", type=Path)
args = parser.parse_args()
SOURCE, TARGET = args.source, args.target

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.top_margin = sec.bottom_margin = Cm(2.35)
sec.left_margin = sec.right_margin = Cm(2.75)

normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(10.5)
normal.font._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
normal.paragraph_format.line_spacing = Pt(16)
normal.paragraph_format.space_after = Pt(0)
normal.paragraph_format.first_line_indent = Pt(21)
normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

for name, size, chinese in [("Title", 19.5, "宋体"), ("Heading 1", 13, "宋体"),
                            ("Heading 2", 10.5, "黑体")]:
    style = doc.styles[name]
    style.font.name = "Times New Roman"
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.font._element.rPr.rFonts.set(qn("w:eastAsia"), chinese)
    style.paragraph_format.space_before = Pt(12)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.first_line_indent = Pt(0)
    if name == "Heading 1":
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for border in style._element.xpath("./w:pPr/w:pBdr"):
        border.getparent().remove(border)

def add_inline(paragraph, text):
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*"):
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)

def add_table(lines):
    cells = [line.strip().strip("|").split("|") for line in lines]
    rows = [cells[0], *cells[2:]]
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Normal Table"
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        rule = OxmlElement(f"w:{edge}")
        rule.set(qn("w:val"), "single" if edge in ("top", "bottom") else "nil")
        if edge in ("top", "bottom"):
            rule.set(qn("w:sz"), "8")
            rule.set(qn("w:color"), "000000")
        borders.append(rule)
    table._tbl.tblPr.append(borders)
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for index, row in enumerate(rows):
        for col, value in enumerate(row):
            p = table.cell(index, col).paragraphs[0]
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.line_spacing = Pt(13)
            p.paragraph_format.space_after = Pt(1)
            if col:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = p.add_run(value.strip())
            run.font.size = Pt(9)
            run.bold = index == 0
            if index == 0:
                tc_borders = OxmlElement("w:tcBorders")
                rule = OxmlElement("w:bottom")
                rule.set(qn("w:val"), "single")
                rule.set(qn("w:sz"), "4")
                rule.set(qn("w:color"), "000000")
                tc_borders.append(rule)
                table.cell(index, col)._tc.get_or_add_tcPr().append(tc_borders)
        keep = OxmlElement("w:cantSplit")
        table.rows[index]._tr.get_or_add_trPr().append(keep)


lines = SOURCE.read_text(encoding="utf-8").splitlines()
pending_table = []
abstract_pending = False
in_references = False
author_pending = False
for idx, line in enumerate([*lines, ""]):
    if line.startswith("|"):
        pending_table.append(line)
        continue
    if pending_table:
        add_table(pending_table)
        pending_table.clear()
    if not line.strip():
        continue
    if abstract_pending or line.startswith("**关键词**"):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.78)
        p.paragraph_format.right_indent = Cm(0.78)
        p.paragraph_format.line_spacing = Pt(15.5)
        if abstract_pending:
            p.add_run("内容提要　").bold = True
        add_inline(p, line)
        abstract_pending = False
        continue
    if line == "## 摘要":
        abstract_pending = True
        continue
    if author_pending:
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(3)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for index, token in enumerate(line.split()):
            if index:
                p.add_run("　")
            name = token.rstrip("¹²")
            p.add_run(name).font.size = Pt(12)
            if token != name:
                marker = p.add_run(token[-1].translate(str.maketrans("¹²", "12")))
                marker.font.superscript = True
                marker.font.size = Pt(9)
        doc.core_properties.author = "、".join(t.rstrip("¹²") for t in line.split())
        author_pending = False
        continue
    if line.startswith(("¹ ", "² ")):
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.line_spacing = Pt(13)
        p.paragraph_format.space_after = Pt(5 if line.startswith("²") else 0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(line[0].translate(str.maketrans("¹²", "12")) + "　" + line[2:]).font.size = Pt(9)
        continue
    if line.startswith("# "):
        p = doc.add_paragraph(style="Title")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_inline(p, line[2:])
        author_pending = True
    elif line.startswith("## "):
        in_references = line == "## 参考文献"
        p = doc.add_paragraph(style="Heading 1")
        add_inline(p, line[3:])
    elif line.startswith("### "):
        p = doc.add_paragraph(style="Heading 2")
        add_inline(p, line[4:])
    elif figure := re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)", line):
        image_path = SOURCE.parent / figure[2]
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.line_spacing = 1
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(image_path), width=Cm(13.7))
        caption = doc.add_paragraph()
        caption.paragraph_format.first_line_indent = Pt(0)
        caption.paragraph_format.space_after = Pt(8)
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.add_run(figure[1]).font.size = Pt(10)
    else:
        p = doc.add_paragraph()
        if in_references:
            p.paragraph_format.left_indent = Pt(14)
            p.paragraph_format.first_line_indent = Pt(-14)
            p.paragraph_format.line_spacing = Pt(13)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_together = True
            run = p.add_run(line)
            run.font.size = Pt(9.5)
            continue
        if line.startswith("Y_ct＝"):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Pt(0)
        if re.match(r"^(?:附表|表)\d", line):
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.first_line_indent = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_inline(p, line)

footer = sec.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer.add_run()
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
run._r.addnext(field)

doc.save(TARGET)
print(TARGET)
