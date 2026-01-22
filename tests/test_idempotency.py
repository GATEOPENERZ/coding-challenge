import pytest
import uuid
from sqlalchemy import select, func
from app.services.import_service import ImportService
from app.models import BankTransaction
from fastapi import HTTPException

@pytest.mark.asyncio
async def test_import_idempotency(db_session):
    service = ImportService(db_session)
    tenant_id = str(uuid.uuid4())
    key = "uniq-key-123"
    
    tx_data = [{
        "amount": 150.0,
        "currency": "USD",
        "posted_at": "2023-01-05T12:00:00",
        "description": "AWS Charge",
        "external_id": "ext-1"
    }]

    result1 = await service.import_transactions(tenant_id, tx_data, key)
    assert result1["count"] == 1
    
    stmt = select(func.count()).select_from(BankTransaction).where(BankTransaction.tenant_id == tenant_id)
    count1 = (await db_session.execute(stmt)).scalar()
    assert count1 == 1

    result2 = await service.import_transactions(tenant_id, tx_data, key)
    
    assert result2 == result1
    
    count2 = (await db_session.execute(stmt)).scalar()
    assert count2 == 1

@pytest.mark.asyncio
async def test_import_conflict_different_payload(db_session):
    service = ImportService(db_session)
    tenant_id = str(uuid.uuid4())
    key = "conflict-key-456"
    
    tx_data_1 = [{
        "amount": 100.0,
        "currency": "USD",
        "posted_at": "2023-01-01T00:00:00",
        "description": "First payload",
        "external_id": "ext-a"
    }]
    
    tx_data_2 = [{
        "amount": 200.0,
        "currency": "EUR",
        "posted_at": "2023-02-01T00:00:00",
        "description": "Different payload",
        "external_id": "ext-b"
    }]

    await service.import_transactions(tenant_id, tx_data_1, key)
    
    with pytest.raises(HTTPException) as exc_info:
        await service.import_transactions(tenant_id, tx_data_2, key)
    
    assert exc_info.value.status_code == 409
    assert "different payload" in exc_info.value.detail.lower()
