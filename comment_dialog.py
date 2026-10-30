"""Janela para digitar o comentário de uma transição.

Roda em processo separado: o Tk exige uma única thread dona da janela, e o pedido vem da thread do
watchdog. Saída: texto no stdout (UTF-8) e código 0; cancelado ou vazio, código 1.
Uso direto: python comment_dialog.py CHAVE-123 "Status destino"
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

LOG = logging.getLogger(__name__)


class TkCommentPrompt:
    """`CommentPrompt` que abre esta janela e espera no máximo `timeout_seconds`."""

    def __init__(self, timeout_seconds: float = 600) -> None:
        self.timeout_seconds = timeout_seconds

    def ask(self, issue_key: str, status: str) -> str | None:
        """Abre a janela e espera; None se cancelada, vazia, com erro ou sem resposta."""
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), issue_key, status],
                check=False,  # cancelamento usa código 1; tratado abaixo
                capture_output=True,
                timeout=self.timeout_seconds,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                # Evita abrir um console vazio junto com a janela quando o pai é python.exe.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            LOG.warning("%s: janela sem resposta em %ss; seguindo sem comentário.", issue_key, self.timeout_seconds)
            return None
        if result.returncode != 0:
            if result.stderr:
                error = result.stderr.decode("utf-8", "replace")[-1000:]
                LOG.error("%s: janela de comentário falhou: %s", issue_key, error)
            return None
        return result.stdout.decode("utf-8")


def main(issue_key: str, status: str) -> int:
    """Mostra a janela e escreve o comentário no stdout. Retorna o código de saída do processo."""
    # Tk só é carregado no processo da janela, nunca no processo do serviço.
    import tkinter as tk  # pylint: disable=import-outside-toplevel
    from tkinter import scrolledtext  # pylint: disable=import-outside-toplevel

    root = tk.Tk()
    root.title(f"Comentário — {issue_key}")
    root.attributes("-topmost", True)
    tk.Label(
        root,
        text=f"{issue_key} foi movida para '{status}'.\nComentário para o Jira (aceita Markdown):",
        justify="left",
    ).pack(anchor="w", padx=10, pady=(10, 4))
    box = scrolledtext.ScrolledText(root, width=90, height=18, wrap="word")
    box.pack(fill="both", expand=True, padx=10)
    box.focus_set()

    submitted: list[str] = []

    def submit(_event=None) -> str:
        submitted.append(box.get("1.0", "end-1c"))
        root.destroy()
        return "break"

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=10, pady=10)
    tk.Button(buttons, text="Comentar (Ctrl+Enter)", command=submit).pack(side="right")
    tk.Button(buttons, text="Mover sem comentário", command=root.destroy).pack(side="right", padx=(0, 8))
    root.bind("<Control-Return>", submit)
    root.mainloop()

    text = submitted[0].strip() if submitted else ""
    if not text:
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
