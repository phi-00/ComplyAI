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

converter = None

def convert_pdf_to_docling_json(pdf_path, output_path=None) -> dict:
    global converter
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"O ficheiro PDF não existe: {pdf_path}")

    print(f"A processar {pdf_path}...")

    if converter is None:
        converter = DocumentConverter()
    document = converter.convert(str(pdf_path)).document

    print(f"\nDocumento processado: {pdf_path}")
    print(f"Número de páginas: {len(document.pages)}")
    document_data = document.export_to_dict()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                document_data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print(f"JSON Docling guardado em: {output_path.resolve()}")
        
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


def save_paragraphs(document: dict, par_output_path: Path | None = None) -> dict:
    result = extract_paragraphs(document)
    
    if par_output_path is not None:
        par_output_path = Path(par_output_path)
        par_output_path.parent.mkdir(parents=True, exist_ok=True)
        with par_output_path.open("w", encoding="utf-8") as file:
            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2,
            )

    print(f"Parágrafos extraídos: {result['paragraph_count']}")
    print(f"JSON de parágrafos guardado em: {par_output_path.resolve()}")
    
    return result


def main() -> None:
    document = convert_pdf_to_docling_json()
    save_paragraphs(document)


if __name__ == "__main__":
    main()
