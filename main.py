"""Project entry point; application flow is implemented in services.report_pipeline."""

from services.report_pipeline import (
    make_report,
    make_type1,
    make_type2,
    run_default_reports,
)


if __name__ == "__main__":
    run_default_reports()
