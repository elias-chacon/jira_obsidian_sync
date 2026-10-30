"""Infraestrutura comum dos testes."""
import shutil
import tempfile
import unittest
from pathlib import Path


def temporary_dir(case: unittest.TestCase) -> Path:
    """Pasta temporária removida ao fim do teste `case`."""
    path = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path
