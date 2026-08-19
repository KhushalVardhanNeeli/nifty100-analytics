import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient

from src.api.main import app

c = TestClient(app)


def test_health():
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["db_row_counts"]["companies"] == 101


def test_companies_list():
    r = c.get("/api/v1/companies")
    assert r.status_code == 200
    assert len(r.json()) >= 92


def test_company_tcs():
    r = c.get("/api/v1/companies/TCS")
    assert r.status_code == 200
    assert r.json()["company"]["ticker"] == "TCS"


def test_company_404():
    assert c.get("/api/v1/companies/INVALID").status_code == 404


def test_screener_roe_filter():
    r = c.get("/api/v1/screener?min_roe=15")
    assert r.status_code == 200
    assert all(x["roe"] >= 15 for x in r.json())


def test_screener_bad_param():
    assert c.get("/api/v1/screener?min_roe=abc").status_code in (400, 422)


def test_sectors_count():
    r = c.get("/api/v1/sectors")
    assert len(r.json()) >= 10


def test_sector_companies():
    r = c.get("/api/v1/sectors/Information%20Technology/companies")
    assert r.status_code == 200
    assert len(r.json()) >= 5


def test_sector_404():
    assert c.get("/api/v1/sectors/UNKNOWN/companies").status_code == 404


def test_portfolio_stats():
    r = c.get("/api/v1/portfolio/stats")
    assert r.status_code == 200
    assert len(r.json()) == 10
