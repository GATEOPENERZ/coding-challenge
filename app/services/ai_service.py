import os
from dotenv import load_dotenv
import httpx
from app.models import Invoice, BankTransaction

load_dotenv()

class AIService:
    def __init__(self):
        self.base_url = os.getenv("AI_API_URL", "https://text.pollinations.ai/")

    async def explain_match(self, invoice: Invoice, tx: BankTransaction) -> str:
        try:
            prompt = (
                f"Explain why this bank transaction matches this invoice concisely. "
                f"Invoice: {invoice.amount} {invoice.currency}, Date: {invoice.invoice_date}, Desc: {invoice.description}. "
                f"Transaction: {tx.amount} {tx.currency}, Date: {tx.posted_at}, Desc: {tx.description}."
            )
            url = f"{self.base_url}{prompt}"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200:
                    return response.text.strip()
                else:
                    raise Exception(f"API Error: {response.status_code}")
        except Exception:
            return f"Heuristic match based on amount similarity ({invoice.amount} == {tx.amount})"