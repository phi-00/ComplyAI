import json
from pathlib import Path

from docling.document_converter import DocumentConverter


PDF_PATH = Path("uploads/teste2.pdf")
DOCLING_OUTPUT_PATH = Path("output/docling.json")
PARAGRAPHS_OUTPUT_PATH = Path("output/paragraphs.json")

# Elementos que queremos manter como conteúdo textual.
CONTENT_LABELS = {
    "text",
    "list_item",
}


def convert_pdf_to_docling_json() -> dict:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"O ficheiro PDF não existe: {PDF_PATH}")

    print(f"A processar {PDF_PATH}...")

    converter = DocumentConverter()
    result = converter.convert(str(PDF_PATH))
    document = result.document

    print(f"\nDocumento processado: {PDF_PATH}")
    print(f"Número de páginas: {len(document.pages)}")

    DOCLING_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document_data = document.export_to_dict()

    with DOCLING_OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            document_data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(f"JSON Docling guardado em: {DOCLING_OUTPUT_PATH.resolve()}")
    return document_data


def extract_paragraphs(document: dict) -> dict:
    paragraphs = []

    for item in document.get("texts", []):
        if item.get("label", "") not in CONTENT_LABELS:
            continue

        text = (item.get("text") or "").strip()
        if not text:
            continue

        pages = sorted(
            {
                provenance.get("page_no")
                for provenance in item.get("prov", [])
                if provenance.get("page_no") is not None
            }
        )
        if not pages:
            continue

        paragraphs.append(
            {
                "id": len(paragraphs) + 1,
                "text": text,
                "pages": pages,
            }
        )

    return {
        "source": document.get("origin", {}).get("filename"),
        "paragraph_count": len(paragraphs),
        "paragraphs": paragraphs,
    }


def save_paragraphs(document: dict) -> None:
    result = extract_paragraphs(document)
    PARAGRAPHS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with PARAGRAPHS_OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Parágrafos extraídos: {result['paragraph_count']}")
    print(f"JSON de parágrafos guardado em: {PARAGRAPHS_OUTPUT_PATH.resolve()}")


def main() -> None:
    document = convert_pdf_to_docling_json()
    save_paragraphs(document)


if __name__ == "__main__":
    main()
