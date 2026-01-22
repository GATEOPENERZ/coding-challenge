import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient):
    resp_a = await client.post("/api/v1/tenants", json={"name": "Tenant A"})
    assert resp_a.status_code == 200
    tenant_a_id = resp_a.json()["id"]

    resp_b = await client.post("/api/v1/tenants", json={"name": "Tenant B"})
    assert resp_b.status_code == 200
    tenant_b_id = resp_b.json()["id"]

    inv_data = {
        "amount": 100.0, 
        "currency": "USD", 
        "invoice_date": "2023-01-01T00:00:00",
        "description": "Service Fee"
    }
    resp_inv = await client.post(f"/api/v1/tenants/{tenant_a_id}/invoices", json=inv_data)
    assert resp_inv.status_code == 200
    
    get_a = await client.get(f"/api/v1/tenants/{tenant_a_id}/invoices")
    assert get_a.status_code == 200
    assert len(get_a.json()) == 1
    assert get_a.json()[0]["tenant_id"] == tenant_a_id

    get_b = await client.get(f"/api/v1/tenants/{tenant_b_id}/invoices")
    assert get_b.status_code == 200
    assert len(get_b.json()) == 0

    resp = await client.post("/api/v1/tenants/invalid-id/invoices", json=inv_data)
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_delete_invoice(client: AsyncClient):
    resp_t = await client.post("/api/v1/tenants", json={"name": "Delete Test"})
    tenant_id = resp_t.json()["id"]
    
    inv_data = {"amount": 50, "currency": "USD", "invoice_date": "2023-01-01T00:00:00"}
    resp_inv = await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json=inv_data)
    invoice_id = resp_inv.json()["id"]
    
    del_resp = await client.delete(f"/api/v1/tenants/{tenant_id}/invoices/{invoice_id}")
    assert del_resp.status_code == 200
    
    get_resp = await client.get(f"/api/v1/tenants/{tenant_id}/invoices")
    assert len(get_resp.json()) == 0

@pytest.mark.asyncio
async def test_list_invoices_with_status_filter(client: AsyncClient):
    resp_t = await client.post("/api/v1/tenants", json={"name": "Filter Test"})
    tenant_id = resp_t.json()["id"]
    
    await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={
        "amount": 100, "currency": "USD", "invoice_date": "2023-01-01T00:00:00"
    })
    await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={
        "amount": 200, "currency": "USD", "invoice_date": "2023-01-02T00:00:00"
    })
    
    all_invoices = await client.get(f"/api/v1/tenants/{tenant_id}/invoices")
    assert len(all_invoices.json()) == 2
    
    open_invoices = await client.get(f"/api/v1/tenants/{tenant_id}/invoices?status=open")
    assert len(open_invoices.json()) == 2
    
    matched_invoices = await client.get(f"/api/v1/tenants/{tenant_id}/invoices?status=matched")
    assert len(matched_invoices.json()) == 0

@pytest.mark.asyncio
async def test_list_invoices_with_amount_filter(client: AsyncClient):
    resp_t = await client.post("/api/v1/tenants", json={"name": "Amount Filter Test"})
    tenant_id = resp_t.json()["id"]
    
    await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={"amount": 50, "currency": "USD"})
    await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={"amount": 150, "currency": "USD"})
    await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={"amount": 300, "currency": "USD"})
    
    filtered = await client.get(f"/api/v1/tenants/{tenant_id}/invoices?amount_min=100&amount_max=200")
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["amount"] == 150

@pytest.mark.asyncio
async def test_confirm_match(client: AsyncClient, db_session):
    resp_t = await client.post("/api/v1/tenants", json={"name": "Match Test"})
    tenant_id = resp_t.json()["id"]
    
    inv = await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={
        "amount": 100, "currency": "USD", "invoice_date": "2023-01-01T00:00:00"
    })
    
    await client.post(f"/api/v1/tenants/{tenant_id}/bank-transactions/import", 
        json=[{
            "amount": 100, "currency": "USD", "posted_at": "2023-01-01T00:00:00", 
            "description": "desc", "external_id": "ext1"
        }],
        headers={"Idempotency-Key": "key1"}
    )
    
    rec = await client.post(f"/api/v1/tenants/{tenant_id}/reconcile")
    candidates = rec.json()
    assert len(candidates) > 0
    match_id = candidates[0]["id"]
    
    conf = await client.post(f"/api/v1/tenants/{tenant_id}/matches/{match_id}/confirm")
    assert conf.status_code == 200
    assert conf.json()["status"] == "confirmed"

@pytest.mark.asyncio
async def test_ai_explanation_endpoint(client: AsyncClient):
    resp_t = await client.post("/api/v1/tenants", json={"name": "AI Test"})
    tenant_id = resp_t.json()["id"]
    
    inv_resp = await client.post(f"/api/v1/tenants/{tenant_id}/invoices", json={
        "amount": 100, "currency": "USD", "invoice_date": "2023-01-01T00:00:00", "description": "Consulting"
    })
    invoice_id = inv_resp.json()["id"]
    
    await client.post(f"/api/v1/tenants/{tenant_id}/bank-transactions/import", 
        json=[{
            "amount": 100, "currency": "USD", "posted_at": "2023-01-01T00:00:00", 
            "description": "Consulting Payment", "external_id": "ext-ai"
        }],
        headers={"Idempotency-Key": "ai-key-1"}
    )
    
    tx_list = await client.get(f"/api/v1/tenants/{tenant_id}/bank-transactions/import")
    
    rec = await client.post(f"/api/v1/tenants/{tenant_id}/reconcile")
    candidates = rec.json()
    tx_id = candidates[0]["transaction_id"]
    
    explain_resp = await client.get(
        f"/api/v1/tenants/{tenant_id}/reconcile/explain?invoice_id={invoice_id}&transaction_id={tx_id}"
    )
    assert explain_resp.status_code == 200
    assert "explanation" in explain_resp.json()
    assert len(explain_resp.json()["explanation"]) > 0
