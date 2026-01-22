from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models import BankTransaction, IdempotencyKey
import hashlib
import json

class ImportService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def import_transactions(
        self, 
        tenant_id: str, 
        transactions_data: List[Dict[str, Any]], 
        idempotency_key: str
    ) -> Dict[str, Any]:
        if not idempotency_key:
             raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

        payload_str = json.dumps(transactions_data, sort_keys=True, default=str)
        current_hash = hashlib.sha256(payload_str.encode()).hexdigest()

        stmt = select(IdempotencyKey).where(
            IdempotencyKey.key == idempotency_key,
            IdempotencyKey.tenant_id == tenant_id
        )
        existing_key = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing_key:
            if existing_key.params_hash and existing_key.params_hash != current_hash:
                 raise HTTPException(status_code=409, detail="Idempotency key reused with different payload")

            if existing_key.response_payload:
                return existing_key.response_payload
            else:
                raise HTTPException(status_code=409, detail="Request currently in progress or failed previously")

        new_key = IdempotencyKey(
            key=idempotency_key, 
            tenant_id=tenant_id, 
            params_hash=current_hash,
            response_payload=None
        )
        self.session.add(new_key)
        
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = (await self.session.execute(stmt)).scalar_one_or_none()
            if existing and existing.response_payload:
                return existing.response_payload
            raise HTTPException(status_code=409, detail="Concurrent request in progress")

        try:
            created_transactions = []
            for tx_data in transactions_data:
                tx = BankTransaction(
                    tenant_id=tenant_id,
                    amount=tx_data["amount"],
                    currency=tx_data["currency"],
                    posted_at=datetime.fromisoformat(tx_data["posted_at"]),
                    description=tx_data["description"],
                    external_id=tx_data["external_id"]
                )
                self.session.add(tx)
                created_transactions.append(tx)
            
            await self.session.commit()
            
            result = {
                "message": "Import successful",
                "count": len(created_transactions),
                "transaction_ids": [t.id for t in created_transactions]
            }

            new_key.response_payload = result
            await self.session.commit()
            
            return result
            
        except Exception as e:
            await self.session.rollback()
            await self.session.delete(new_key)
            await self.session.commit()
            raise e
