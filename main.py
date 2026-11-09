from pathlib import Path

import config
from extractors.pdf_to_text import pdf_to_text
from extractors.typr1_reader import read_type1_pdf
from services.time_utils import reconcile
from services.type1_report import Type1Report
from services.type2_report import Type2Report


def make_type1(pdf_name: str, year: int, month: int, seed: int | None = None) -> Path:
    raw = read_type1_pdf(str(config.PDF_DIR / pdf_name))
    clean = [reconcile(r.entry, r.exit, r.total) for r in raw]

    report = Type1Report()
    report.learn(clean)
    data = report.generate(year, month, seed=seed)
    return report.build_pdf(data, config.OUTPUT_DIR / f"{Path(pdf_name).stem}_generated.pdf")


def make_type2(pdf_name: str, year: int, month: int, seed: int | None = None) -> Path:
    text = pdf_to_text(str(config.PDF_DIR / pdf_name))

    report = Type2Report()
    report.parse_text(text)
    data = report.generate(year, month, seed=seed)
    return report.build_pdf(data, config.OUTPUT_DIR / f"{Path(pdf_name).stem}_generated.pdf")


if __name__ == "__main__":
    # TODO: report_detector will choose between the two functions automatically
    print(make_type1("type1_1.pdf", 2026, 3, seed=7))
    print(make_type2("type2_1.pdf", 2026, 3, seed=7))