"""Build the Word report from verified GitHub Actions terminal screenshots."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


HERE = Path(__file__).resolve().parent
RUN_URL = "https://github.com/breevasofa/23---11/actions/runs/45678136136"
IMAGES = [
    ("00_initial.png", "Исходный кластер: 4 мастера и 8 реплик"),
    ("01_two_replicas.png", "К выбранному мастеру добавлены две реплики"),
    ("02_removed.png", "Одна из добавленных реплик удалена"),
    ("03_new_master.png", "Тот же порт добавлен заново как мастер без слотов"),
    ("04_resharded.png", "64 слота и 64 ключа перенесены на новый мастер"),
]
for filename, _ in IMAGES:
    assert (HERE / "screenshots" / filename).is_file(), filename

document = Document()
section = document.sections[0]
section.page_width = Inches(8.5)
section.page_height = Inches(11)
section.top_margin = Inches(.7)
section.bottom_margin = Inches(.7)
section.left_margin = Inches(.75)
section.right_margin = Inches(.75)

normal = document.styles["Normal"]
normal.font.name = "Arial"
normal.font.size = Pt(10.5)
normal.paragraph_format.space_after = Pt(7)
normal.paragraph_format.line_spacing = 1.12
for name, size in [("Title", 18), ("Heading 1", 12)]:
    style = document.styles[name]
    style.font.name = "Arial"
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_before = Pt(10)
    style.paragraph_format.space_after = Pt(5)


def link(paragraph, title: str, url: str) -> None:
    relation = paragraph.part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relation)
    run = OxmlElement("w:r")
    style = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "1658A0")
    style.append(color)
    run.append(style)
    text = OxmlElement("w:t")
    text.text = title
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def image(index: int) -> None:
    filename, caption = IMAGES[index]
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.add_run().add_picture(str(HERE / "screenshots" / filename), width=Inches(6.6))
    caption_line = document.add_paragraph(f"Рисунок {index + 1}. {caption}")
    caption_line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_line.paragraph_format.space_after = Pt(11)
    for run in caption_line.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(65, 65, 65)


document.add_paragraph("Масштабирование кластера Redis", "Title")
document.add_paragraph(
    "Вариант 2, порты 4000–4013. В GitHub Actions воспроизведено добавление "
    "двух реплик, удаление и повторное добавление одной из них как мастера, "
    "затем перенос данных на новый мастер."
)
paragraph = document.add_paragraph("Подтверждённый запуск: ")
link(paragraph, "GitHub Actions", RUN_URL)
document.add_heading("Проверки по этапам", level=1)
table = document.add_table(rows=1, cols=3)
table.style = "Table Grid"
for cell, label in zip(table.rows[0].cells, ["Этап", "Узлы", "Результат проверки"]):
    cell.text = label
for values in [
    ("Исходный", "4 мастера, 8 реплик", "16 384 слота; 64 ключа читаются"),
    ("Добавление", "4 мастера, 10 реплик", "4012 и 4013 реплицируют один мастер"),
    ("Удаление", "4 мастера, 9 реплик", "4013 отсутствует; кластер работает"),
    ("Новый мастер", "5 мастеров, 9 реплик", "4013 получил новый ID и пока 0 слотов"),
    ("Решардирование", "5 мастеров, 9 реплик", "4013 получил 64 слота и 64 ключа"),
]:
    for cell, value in zip(table.add_row().cells, values):
        cell.text = value
for row in table.rows:
    for cell in row.cells:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

document.add_paragraph(
    "На каждом этапе подтверждены cluster_state:ok, покрытие всех 16 384 слотов "
    "командой redis-cli --cluster check и чтение всех проверочных ключей. "
    "После переноса дополнительно проверено DBSIZE=64 на новом мастере."
)
document.add_heading("Исходное состояние", level=1)
image(0)

heading = document.add_heading("Добавление и удаление реплик", level=1)
heading.paragraph_format.page_break_before = True
image(1)
image(2)

heading = document.add_heading("Новый мастер и перенос данных", level=1)
heading.paragraph_format.page_break_before = True
image(3)
image(4)
document.add_heading("Вывод", level=1)
document.add_paragraph(
    "Кластер сохранил работоспособность при добавлении и удалении реплик. "
    "Повторно добавленный узел :4013 стал мастером и после решардирования получил "
    "64 слота с 64 проверочными ключами; все значения остались доступны."
)

output = HERE / "Отчёт_масштабирование_Redis_Cluster.docx"
document.save(output)
print(output)
