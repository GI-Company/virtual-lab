import pytest

pytest.importorskip('jwt')
pytest.importorskip('starlette')
pytest.importorskip('httpx')

from starlette.testclient import TestClient
from scripts.research_service_fixture import seed_synthetic_fixture
from virtual_lab.integrations.research_service.server import create_app


@pytest.fixture
def fixture(tmp_path):
    return seed_synthetic_fixture(tmp_path/'qualification')


@pytest.fixture
def client(fixture):
    app = create_app(root=fixture.root,policy_path=fixture.policy_path,audit_path=fixture.audit_path,
                     verifier=fixture.verifier,allowed_hosts=['testserver'])
    with TestClient(app, headers={'Authorization':'Bearer '+fixture.token()}) as connection:
        yield connection
