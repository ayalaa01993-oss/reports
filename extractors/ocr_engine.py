"""Single integration point for the pytesseract dependency."""

import pytesseract

import config

pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


def image_to_string(image, *, lang: str, config: str) -> str:
    return pytesseract.image_to_string(image, lang=lang, config=config)


def image_to_data(image, *, lang: str, config: str) -> dict[str, list]:
    return pytesseract.image_to_data(
        image,
        lang=lang,
        config=config,
        output_type=pytesseract.Output.DICT,
    )
