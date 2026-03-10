"""Backend API tests for RADAR."""

import uuid


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["name"] == "RADAR"


class TestProjectCRUD:
    def test_create_project(self, client):
        response = client.post(
            "/api/projects",
            json={"name": "MDR Surveillance", "description": "Multi-drug resistance study"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "MDR Surveillance"
        assert data["description"] == "Multi-drug resistance study"
        assert "id" in data

    def test_create_project_minimal(self, client):
        response = client.post("/api/projects", json={"name": "Minimal"})
        assert response.status_code == 201
        assert response.json()["name"] == "Minimal"

    def test_list_projects(self, client):
        client.post("/api/projects", json={"name": "A"})
        client.post("/api/projects", json={"name": "B"})
        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_get_project(self, client):
        resp = client.post("/api/projects", json={"name": "Get Test"})
        pid = resp.json()["id"]
        response = client.get(f"/api/projects/{pid}")
        assert response.status_code == 200
        assert response.json()["name"] == "Get Test"

    def test_get_project_not_found(self, client):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/projects/{fake_id}")
        assert response.status_code == 404

    def test_update_project(self, client):
        resp = client.post("/api/projects", json={"name": "Original", "description": "Orig"})
        pid = resp.json()["id"]
        response = client.put(f"/api/projects/{pid}", json={"name": "Updated"})
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_delete_project(self, client):
        resp = client.post("/api/projects", json={"name": "To Delete"})
        pid = resp.json()["id"]
        response = client.delete(f"/api/projects/{pid}")
        assert response.status_code == 204
        assert client.get(f"/api/projects/{pid}").status_code == 404


class TestSamples:
    def _create_project(self, client):
        resp = client.post("/api/projects", json={"name": "Sample Project"})
        return resp.json()["id"]

    def test_create_sample(self, client):
        pid = self._create_project(client)
        response = client.post(
            f"/api/projects/{pid}/samples",
            json={"name": "ISOLATE_001", "input_type": "fastq"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "ISOLATE_001"
        assert data["status"] == "pending"

    def test_create_sample_invalid_project(self, client):
        fake_id = str(uuid.uuid4())
        response = client.post(
            f"/api/projects/{fake_id}/samples",
            json={"name": "ORPHAN"},
        )
        assert response.status_code == 404

    def test_list_samples(self, client):
        pid = self._create_project(client)
        client.post(f"/api/projects/{pid}/samples", json={"name": "S1"})
        client.post(f"/api/projects/{pid}/samples", json={"name": "S2"})
        response = client.get(f"/api/projects/{pid}/samples")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_get_sample(self, client):
        pid = self._create_project(client)
        sresp = client.post(f"/api/projects/{pid}/samples", json={"name": "GET_ME"})
        sid = sresp.json()["id"]
        response = client.get(f"/api/samples/{sid}")
        assert response.status_code == 200
        assert response.json()["name"] == "GET_ME"

    def test_delete_sample(self, client):
        pid = self._create_project(client)
        sresp = client.post(f"/api/projects/{pid}/samples", json={"name": "DEL_ME"})
        sid = sresp.json()["id"]
        response = client.delete(f"/api/samples/{sid}")
        assert response.status_code == 204


class TestMetadata:
    def _create_sample(self, client):
        pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
        sid = client.post(f"/api/projects/{pid}/samples", json={"name": "S"}).json()["id"]
        return sid

    def test_upsert_metadata(self, client):
        sid = self._create_sample(client)
        response = client.put(
            f"/api/samples/{sid}/metadata",
            json={"source": "blood culture", "species": "E. coli"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "blood culture"
        assert data["species"] == "E. coli"

    def test_get_metadata(self, client):
        sid = self._create_sample(client)
        client.put(f"/api/samples/{sid}/metadata", json={"source": "urine"})
        response = client.get(f"/api/samples/{sid}/metadata")
        assert response.status_code == 200
        assert response.json()["source"] == "urine"

    def test_add_ast_result(self, client):
        sid = self._create_sample(client)
        response = client.post(
            f"/api/samples/{sid}/ast",
            json={"antibiotic": "ampicillin", "sir": "R", "mic": ">=32"},
        )
        assert response.status_code == 201
        assert response.json()["antibiotic"] == "ampicillin"
        assert response.json()["sir"] == "R"
