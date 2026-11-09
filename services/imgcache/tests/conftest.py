import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.models import Base
from app.database import override_engine
from app.storage import override_storage, reset_storage
from app.storage.local import LocalStorage


@pytest.fixture
def app(tmp_path):
    import app.metrics as m_module
    m_module._unregister_prometheus_reader()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    override_engine(engine)
    override_storage(LocalStorage(str(tmp_path / "storage")))

    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
    reset_storage()


@pytest.fixture(scope="session")
def minio_container():
    try:
        from testcontainers.minio import MinioContainer
        container = MinioContainer()
        container.start()
        yield container
        container.stop()
    except Exception:
        pytest.skip("Docker not available")


@pytest.fixture
def s3_client(minio_container, tmp_path):
    host = minio_container.get_container_host_ip()
    port = minio_container.get_exposed_port(9000)
    endpoint = f"http://{host}:{port}"

    from app.storage.s3 import S3Storage
    override_storage(S3Storage(
        bucket="test-imgcache",
        endpoint_url=endpoint,
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
    ))
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    override_engine(engine)

    from app.main import app as fastapi_app
    with TestClient(fastapi_app) as c:
        yield c
    reset_storage()
