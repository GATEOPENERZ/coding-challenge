import strawberry
from typing import List, Optional
from strawberry.types import Info
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app import models
from app.services.reconciliation import ReconciliationService
from app.services.ai_service import AIService
from app.services.import_service import ImportService

@strawberry.input
class CreateTenantInput:
    name: str

@strawberry.input
class CreateInvoiceInput:
    amount: float
    currency: str = "USD"
    invoice_date: Optional[str] = None
    description: Optional[str] = None
    invoice_number: Optional[str] = None
    vendor_id: Optional[str] = None

@strawberry.input
class TransactionInput:
    amount: float
    currency: str = "USD"
    posted_at: str
    description: str
    external_id: Optional[str] = None

@strawberry.input
class ImportTransactionsInput:
    transactions: List[TransactionInput]

@strawberry.type
class TenantType:
    id: str
    name: str
    created_at: str

@strawberry.type
class InvoiceType:
    id: str
    amount: float
    currency: str
    invoice_date: Optional[str]
    status: str
    description: Optional[str]
    invoice_number: Optional[str]
    vendor_id: Optional[str]
    created_at: str

@strawberry.type
class TransactionType:
    id: str
    amount: float
    currency: str
    posted_at: str
    description: str
    external_id: Optional[str]
    created_at: str

@strawberry.type
class MatchCandidateType:
    id: str
    invoice_id: str
    transaction_id: str
    score: float
    status: str
    created_at: str

@strawberry.type
class ImportResultType:
    message: str
    count: int
    transaction_ids: List[str]

@strawberry.type
class Query:
    @strawberry.field
    async def tenants(self, info: Info) -> List[TenantType]:
        db: AsyncSession = info.context["db"]
        result = await db.execute(select(models.Tenant))
        tenants = result.scalars().all()
        return [
            TenantType(
                id=t.id, 
                name=t.name, 
                created_at=t.created_at.isoformat()
            ) for t in tenants
        ]

    @strawberry.field
    async def invoices(
        self, 
        info: Info, 
        tenant_id: str,
        status: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[InvoiceType]:
        db: AsyncSession = info.context["db"]
        query = select(models.Invoice).where(models.Invoice.tenant_id == tenant_id)
        if status:
            query = query.where(models.Invoice.status == status)
        if amount_min is not None:
            query = query.where(models.Invoice.amount >= amount_min)
        if amount_max is not None:
            query = query.where(models.Invoice.amount <= amount_max)
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        invoices = result.scalars().all()
        return [
            InvoiceType(
                id=i.id,
                amount=i.amount,
                currency=i.currency,
                invoice_date=i.invoice_date.isoformat() if i.invoice_date else None,
                status=i.status,
                description=i.description,
                invoice_number=i.invoice_number,
                vendor_id=i.vendor_id,
                created_at=i.created_at.isoformat()
            ) for i in invoices
        ]

    @strawberry.field
    async def bank_transactions(
        self, 
        info: Info, 
        tenant_id: str,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TransactionType]:
        db: AsyncSession = info.context["db"]
        query = select(models.BankTransaction).where(models.BankTransaction.tenant_id == tenant_id)
        if amount_min is not None:
            query = query.where(models.BankTransaction.amount >= amount_min)
        if amount_max is not None:
            query = query.where(models.BankTransaction.amount <= amount_max)
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        transactions = result.scalars().all()
        return [
            TransactionType(
                id=t.id,
                amount=t.amount,
                currency=t.currency,
                posted_at=t.posted_at.isoformat(),
                description=t.description,
                external_id=t.external_id,
                created_at=t.created_at.isoformat()
            ) for t in transactions
        ]

    @strawberry.field
    async def match_candidates(
        self, 
        info: Info, 
        tenant_id: str,
        status: Optional[str] = None
    ) -> List[MatchCandidateType]:
        db: AsyncSession = info.context["db"]
        query = select(models.MatchCandidate).where(models.MatchCandidate.tenant_id == tenant_id)
        if status:
            query = query.where(models.MatchCandidate.status == status)
        result = await db.execute(query)
        matches = result.scalars().all()
        return [
            MatchCandidateType(
                id=m.id,
                invoice_id=m.invoice_id,
                transaction_id=m.transaction_id,
                score=m.score,
                status=m.status.value if hasattr(m.status, 'value') else m.status,
                created_at=m.created_at.isoformat()
            ) for m in matches
        ]

    @strawberry.field
    async def explain_reconciliation(
        self, 
        info: Info, 
        tenant_id: str,
        invoice_id: str, 
        transaction_id: str
    ) -> str:
        db: AsyncSession = info.context["db"]
        invoice = await db.get(models.Invoice, invoice_id)
        transaction = await db.get(models.BankTransaction, transaction_id)
        if not invoice or not transaction:
            return "Error: Invoice or Transaction not found"
        if invoice.tenant_id != tenant_id or transaction.tenant_id != tenant_id:
            return "Error: Resource mismatch for tenant"
        service = AIService()
        return await service.explain_match(invoice, transaction)

@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_tenant(self, info: Info, input: CreateTenantInput) -> TenantType:
        db: AsyncSession = info.context["db"]
        new_tenant = models.Tenant(name=input.name)
        db.add(new_tenant)
        await db.commit()
        await db.refresh(new_tenant)
        return TenantType(
            id=new_tenant.id, 
            name=new_tenant.name, 
            created_at=new_tenant.created_at.isoformat()
        )

    @strawberry.mutation
    async def create_invoice(self, info: Info, tenant_id: str, input: CreateInvoiceInput) -> InvoiceType:
        db: AsyncSession = info.context["db"]
        tenant = await db.get(models.Tenant, tenant_id)
        if not tenant:
            raise Exception("Tenant not found")
        new_invoice = models.Invoice(
            tenant_id=tenant_id,
            amount=input.amount,
            currency=input.currency,
            invoice_date=datetime.fromisoformat(input.invoice_date) if input.invoice_date else None,
            description=input.description,
            invoice_number=input.invoice_number,
            vendor_id=input.vendor_id
        )
        db.add(new_invoice)
        await db.commit()
        await db.refresh(new_invoice)
        return InvoiceType(
            id=new_invoice.id,
            amount=new_invoice.amount,
            currency=new_invoice.currency,
            invoice_date=new_invoice.invoice_date.isoformat() if new_invoice.invoice_date else None,
            status=new_invoice.status,
            description=new_invoice.description,
            invoice_number=new_invoice.invoice_number,
            vendor_id=new_invoice.vendor_id,
            created_at=new_invoice.created_at.isoformat()
        )

    @strawberry.mutation
    async def import_bank_transactions(
        self, 
        info: Info, 
        tenant_id: str, 
        input: ImportTransactionsInput,
        idempotency_key: str
    ) -> ImportResultType:
        db: AsyncSession = info.context["db"]
        service = ImportService(db)
        tx_data = [
            {
                "amount": t.amount,
                "currency": t.currency,
                "posted_at": t.posted_at,
                "description": t.description,
                "external_id": t.external_id
            } for t in input.transactions
        ]
        result = await service.import_transactions(tenant_id, tx_data, idempotency_key)
        return ImportResultType(
            message=result["message"],
            count=result["count"],
            transaction_ids=result["transaction_ids"]
        )

    @strawberry.mutation
    async def reconcile(self, info: Info, tenant_id: str) -> List[MatchCandidateType]:
        db: AsyncSession = info.context["db"]
        service = ReconciliationService(db)
        candidates = await service.reconcile(tenant_id)
        return [
            MatchCandidateType(
                id=c.id,
                invoice_id=c.invoice_id,
                transaction_id=c.transaction_id,
                score=c.score,
                status=c.status.value if hasattr(c.status, 'value') else c.status,
                created_at=c.created_at.isoformat()
            ) for c in candidates
        ]

    @strawberry.mutation
    async def confirm_match(self, info: Info, tenant_id: str, match_id: str) -> MatchCandidateType:
        db: AsyncSession = info.context["db"]
        match = await db.get(models.MatchCandidate, match_id)
        if not match or match.tenant_id != tenant_id:
            raise Exception("Match not found")
        match.status = models.MatchStatus.CONFIRMED
        await db.commit()
        await db.refresh(match)
        return MatchCandidateType(
            id=match.id,
            invoice_id=match.invoice_id,
            transaction_id=match.transaction_id,
            score=match.score,
            status=match.status.value,
            created_at=match.created_at.isoformat()
        )

    @strawberry.mutation
    async def delete_invoice(self, info: Info, tenant_id: str, invoice_id: str) -> bool:
        db: AsyncSession = info.context["db"]
        invoice = await db.get(models.Invoice, invoice_id)
        if not invoice or invoice.tenant_id != tenant_id:
            return False
        await db.delete(invoice)
        await db.commit()
        return True

schema = strawberry.Schema(query=Query, mutation=Mutation)