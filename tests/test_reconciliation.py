import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
import httpx
from app.services.reconciliation import ReconciliationService
from app.services.ai_service import AIService
from app.models import Invoice, BankTransaction, MatchStatus, Tenant

@pytest.mark.asyncio
async def test_reconciliation_heuristics(db_session):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    tenant_id = tenant.id
    
    service = ReconciliationService(db_session)
    
    inv1 = Invoice(tenant_id=tenant_id, amount=100.0, currency="USD", invoice_date=datetime.now(), status="open")
    tx1 = BankTransaction(tenant_id=tenant_id, amount=100.0, currency="USD", posted_at=datetime.now(), description="Payment", external_id="1")
    
    inv2 = Invoice(tenant_id=tenant_id, amount=500.0, currency="USD", invoice_date=datetime.now(), status="open")
    
    db_session.add_all([inv1, tx1, inv2])
    await db_session.commit()
    
    candidates = await service.reconcile(tenant_id)
    
    assert len(candidates) >= 1
    match = candidates[0]
    assert match.invoice_id == inv1.id
    assert match.transaction_id == tx1.id
    assert match.score >= 0.6
    assert match.status == MatchStatus.PROPOSED

@pytest.mark.asyncio
async def test_reconciliation_ranking(db_session):
    tenant = Tenant(name="Ranking Tenant")
    db_session.add(tenant)
    await db_session.commit()
    tenant_id = tenant.id
    
    service = ReconciliationService(db_session)
    now = datetime.now()
    
    inv1 = Invoice(tenant_id=tenant_id, amount=100.0, currency="USD", invoice_date=now, status="open", description="Consulting")
    inv2 = Invoice(tenant_id=tenant_id, amount=100.0, currency="USD", invoice_date=now, status="open", description="Other")
    tx1 = BankTransaction(tenant_id=tenant_id, amount=100.0, currency="USD", posted_at=now, description="Consulting Payment", external_id="rank1")
    
    db_session.add_all([inv1, inv2, tx1])
    await db_session.commit()
    
    candidates = await service.reconcile(tenant_id)
    
    inv1_match = next((c for c in candidates if c.invoice_id == inv1.id), None)
    inv2_match = next((c for c in candidates if c.invoice_id == inv2.id), None)
    
    assert inv1_match is not None
    assert inv2_match is not None
    assert inv1_match.score > inv2_match.score

@pytest.mark.asyncio
async def test_ai_fallback_on_error():
    service = AIService()
    inv = Invoice(amount=100.0, currency="USD", invoice_date=datetime.now(), description="Consulting")
    tx = BankTransaction(amount=100.0, currency="USD", posted_at=datetime.now(), description="Consulting Inv", external_id="1")
    
    with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Network error")
        explanation = await service.explain_match(inv, tx)
    
    assert isinstance(explanation, str)
    assert len(explanation) > 0
    assert "Heuristic" in explanation or "100.0" in explanation

@pytest.mark.asyncio
async def test_ai_success_path():
    service = AIService()
    inv = Invoice(amount=100.0, currency="USD", invoice_date=datetime.now(), description="Consulting")
    tx = BankTransaction(amount=100.0, currency="USD", posted_at=datetime.now(), description="Consulting Inv", external_id="1")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "This is a strong match because both amounts are exactly $100 USD."
    
    with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        explanation = await service.explain_match(inv, tx)
    
    assert "strong match" in explanation.lower() or "100" in explanation
