import pytest

from emporio.config import get_settings


@pytest.fixture
def settings_env(monkeypatch):
    """Permite alterar variáveis de ambiente e recarregar a configuração."""

    def _set(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()
