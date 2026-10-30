"""Garante uma única instância do sincronizador por máquina (DT-03): duas disputariam o mesmo board.

Usa um lock exclusivo do sistema operacional num arquivo. Se o processo morrer, o sistema libera o lock; o arquivo
pode continuar existindo, e isso não impede a próxima execução.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import IO

if os.name == "nt":
    import msvcrt

    def _lock(handle: IO[str]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle: IO[str]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl  # pylint: disable=import-error  # só existe em POSIX; este ramo não roda no Windows

    def _lock(handle: IO[str]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle: IO[str]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class AlreadyRunningError(RuntimeError):
    """Outra instância do sincronizador já detém o lock."""


class InstanceLock:
    """Lock exclusivo em `path`, mantido do `acquire()` ao `release()`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    def acquire(self) -> None:
        """AlreadyRunningError se outra instância estiver rodando; não espera."""
        handle = self.path.open("a+", encoding="utf-8")
        try:
            _lock(handle)
        except OSError as exc:
            handle.close()
            raise AlreadyRunningError(f"Outra instância já está rodando (lock em {self.path})") from exc
        self._handle = handle

    def release(self) -> None:
        """Libera o lock; sem efeito se ele não estiver sendo mantido."""
        if self._handle is None:
            return
        try:
            _unlock(self._handle)
        finally:
            self._handle.close()
            self._handle = None
