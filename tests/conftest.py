from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from emporio.config import PROJECT_ROOT, get_settings

TEST_PEPPER = "pepper-de-teste"
CAMPO_GRANDE = ZoneInfo("America/Campo_Grande")


@pytest.fixture
def settings_env(monkeypatch):
    """Permite alterar variáveis de ambiente e recarregar a configuração."""

    def _set(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def store_db(tmp_path_factory):
    """Banco gerado pelo ETL a partir dos dados reais, compartilhado entre os testes."""
    from emporio.etl import run_pipeline

    out = tmp_path_factory.mktemp("store")
    result = run_pipeline(
        raw_dir=PROJECT_ROOT / "data" / "raw",
        db_path=out / "store.db",
        report_path=None,
        pepper=TEST_PEPPER,
    )
    return result.db_path


@pytest.fixture
def make_ctx(store_db):
    """Cria um ToolContext com o "agora" desejado (padrão: sábado, 31/10/2026, 10h30)."""
    from emporio.tools import ToolContext

    def _make(now: str = "2026-10-31T10:30", session_id: str = "teste", guard=None):
        moment = datetime.fromisoformat(now).replace(tzinfo=CAMPO_GRANDE)
        ctx = ToolContext(db_path=store_db, now=moment, pepper=TEST_PEPPER, session_id=session_id)
        if guard is not None:
            ctx.guard = guard
        return ctx

    return _make
