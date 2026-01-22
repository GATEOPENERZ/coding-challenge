from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app import models, schemas
from app.services.reconciliation import ReconciliationService
from app.services.import_service import ImportService
from app.services.ai_service import AIService

router = APIRouter()

@router.post("/tenants", response_model=schemas.TenantResponse)
async def create_tenant(tenant: schemas.TenantCreate, db: AsyncSession = Depends(get_db)):
    new_tenant = models.Tenant(name=tenant.name)
    db.add(new_tenant)
    await db.commit()
    await db.refresh(new_tenant)
    return new_tenant

@router.get("/tenants", response_model=List[schemas.TenantResponse])
async def list_tenants(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Tenant))
    return result.scalars().all()

@router.post("/tenants/{tenant_id}/invoices", response_model=schemas.InvoiceResponse)
async def create_invoice(
    tenant_id: str, 
    invoice: schemas.InvoiceCreate, 
    db: AsyncSession = Depends(get_db)
):
    tenant = await db.get(models.Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    new_invoice = models.Invoice(
        tenant_id=tenant_id,
        **invoice.model_dump()
    )
    db.add(new_invoice)
    await db.commit()
    await db.refresh(new_invoice)
    return new_invoice

@router.get("/tenants/{tenant_id}/invoices", response_model=List[schemas.InvoiceResponse])
async def list_invoices(
    tenant_id: str,
    status: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    amount_min: Optional[float] = Query(None),
    amount_max: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(models.Invoice).where(models.Invoice.tenant_id == tenant_id)
    if status:
        query = query.where(models.Invoice.status == status)
    if vendor_id:
        query = query.where(models.Invoice.vendor_id == vendor_id)
    if date_from:
        query = query.where(models.Invoice.invoice_date >= date_from)
    if date_to:
        query = query.where(models.Invoice.invoice_date <= date_to)
    if amount_min is not None:
        query = query.where(models.Invoice.amount >= amount_min)
    if amount_max is not None:
        query = query.where(models.Invoice.amount <= amount_max)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/tenants/{tenant_id}/bank-transactions/import", response_model=schemas.ImportResponse)
async def import_transactions(
    tenant_id: str,
    transactions: List[schemas.TransactionCreate],
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db)
):
    service = ImportService(db)
    tx_data = [tx.model_dump() for tx in transactions]
    return await service.import_transactions(tenant_id, tx_data, idempotency_key)

@router.post("/tenants/{tenant_id}/reconcile", response_model=List[schemas.MatchCandidateResponse])
async def reconcile_invoices(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    service = ReconciliationService(db)
    return await service.reconcile(tenant_id)

@router.delete("/tenants/{tenant_id}/invoices/{invoice_id}")
async def delete_invoice(
    tenant_id: str,
    invoice_id: str,
    db: AsyncSession = Depends(get_db)
):
    invoice = await db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    await db.delete(invoice)
    await db.commit()
    return {"message": "Invoice deleted"}

@router.post("/tenants/{tenant_id}/matches/{match_id}/confirm", response_model=schemas.MatchCandidateResponse)
async def confirm_match(
    tenant_id: str,
    match_id: str,
    db: AsyncSession = Depends(get_db)
):
    match = await db.get(models.MatchCandidate, match_id)
    if not match or match.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Match not found")
    match.status = models.MatchStatus.CONFIRMED
    await db.commit()
    await db.refresh(match)
    return match

@router.get("/tenants/{tenant_id}/reconcile/explain", response_model=schemas.MatchExplanationResponse)
async def explain_match(
    tenant_id: str,
    invoice_id: str,
    transaction_id: str,
    db: AsyncSession = Depends(get_db)
):
    invoice = await db.get(models.Invoice, invoice_id)
    transaction = await db.get(models.BankTransaction, transaction_id)
    if not invoice or not transaction:
        raise HTTPException(status_code=404, detail="Invoice or Transaction not found")
    if invoice.tenant_id != tenant_id or transaction.tenant_id != tenant_id:
         raise HTTPException(status_code=403, detail="Resource mismatch for tenant")
    service = AIService()
    explanation = await service.explain_match(invoice, transaction)
    return schemas.MatchExplanationResponse(explanation=explanation)