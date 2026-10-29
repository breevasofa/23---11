"""Run the assignment notebook and keep its real output for GitHub."""

from pathlib import Path

import nbformat
from nbclient import NotebookClient


source = Path(__file__).with_name("redis_uk.ipynb")
target = source.with_name("redis_uk_executed.ipynb")
notebook = nbformat.read(source, as_version=4)
NotebookClient(notebook, timeout=180, kernel_name="python3").execute()
nbformat.write(notebook, target)

for cell in notebook.cells:
    for output in cell.get("outputs", []):
        if output.get("output_type") == "stream":
            print(output.get("text", ""), end="")
print(f"Выполненный notebook: {target}")
