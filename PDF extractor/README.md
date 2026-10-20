## Como correr o conversor

Abra um terminal na pasta principal do projeto e siga estes passos:

1. Instale as dependências definidas no `requirements.txt`:

   ```bash
   python -m pip install -r requirements.txt
   ```

2. Abra o ficheiro `extrator/docling_converter.py` e altere a variável
   `PDF_PATH` para o caminho do PDF que pretende converter. Por exemplo:

   ```python
   PDF_PATH = Path("uploads/teste2.pdf")
   ```

3. Execute o conversor no terminal:

   ```bash
   python -m extrator.docling_converter
   ```

Os ficheiros gerados são guardados na pasta `output`:

- `output/docling.json`
- `output/paragraphs.json`