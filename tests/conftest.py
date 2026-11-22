import os
os.environ["APP_ENV"] = "test"
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.models import Base
from backend.database import get_db, engine as disk_engine, Base as DiskBase, SessionLocal
from backend.main import app
from backend.services.llm_client import llm_client

# In-memory test database with StaticPool to share connection across threads
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def ensure_disk_db_schema():
    """Ensures tables exist on disk SQLite database for tests using SessionLocal."""
    DiskBase.metadata.create_all(bind=disk_engine)

@pytest.fixture(scope="function")
def db_session():
    """Creates a fresh in-memory database schema for each test."""
    llm_client.set_provider("mock")
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    llm_client.set_provider("mock") # Always deterministic mock in tests
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

