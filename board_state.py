"""Estado do board compartilhado entre as duas direções de sincronização."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class BoardState:
    """Estado compartilhado entre as duas direções de sincronização.

    `synced_content` é o último conteúdo do board sabidamente consistente com o Jira
    (texto com quebras de linha normalizadas para "\\n"). Leia e altere apenas com `lock` adquirido.
    """

    lock: threading.Lock = field(default_factory=threading.Lock)
    synced_content: str | None = None
