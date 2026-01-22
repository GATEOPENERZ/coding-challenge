from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Invoice, BankTransaction, MatchCandidate, MatchStatus
from difflib import SequenceMatcher

class ReconciliationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reconcile(self, tenant_id: str) -> List[MatchCandidate]:
        stmt_invoices = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == "open"
        )
        invoices = (await self.session.execute(stmt_invoices)).scalars().all()

        stmt_transactions = select(BankTransaction).where(
            BankTransaction.tenant_id == tenant_id
        )
        transactions = (await self.session.execute(stmt_transactions)).scalars().all()
        
        candidates = []

        for invoice in invoices:
            for tx in transactions:
                score = self._calculate_score(invoice, tx)
                if score > 0.3:
                    candidate = MatchCandidate(
                        tenant_id=tenant_id,
                        invoice_id=invoice.id,
                        transaction_id=tx.id,
                        score=score,
                        status=MatchStatus.PROPOSED
                    )
                    candidates.append(candidate)
                    self.session.add(candidate)
        
        await self.session.commit()
        return rounded_candidates(sorted(candidates, key=lambda x: x.score, reverse=True))

    def _calculate_score(self, invoice: Invoice, tx: BankTransaction) -> float:
        score = 0.0
        
        if abs(invoice.amount - tx.amount) < 0.01 and invoice.currency == tx.currency:
            score += 0.6
        
        if invoice.invoice_date:
            date_diff = abs((invoice.invoice_date - tx.posted_at).days)
            if date_diff <= 3:
                score += 0.2
            elif date_diff <= 7:
                score += 0.1
            
        if invoice.description and tx.description:
            similarity = SequenceMatcher(None, invoice.description.lower(), tx.description.lower()).ratio()
            score += (similarity * 0.2)
            
        return min(round(score, 3), 1.0)

def rounded_candidates(candidates: List[MatchCandidate]) -> List[MatchCandidate]:
    return candidates
