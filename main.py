# main.py
from locale import currency

from fastapi import FastAPI, HTTPException, Query, Depends, Request 
import os
import requests
import re
import logging
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models import RequestPayment, SendPayment, ValidateMsisdn, generate_reference, RelworxWebhookPayload
from database import engine, Base, get_db
from models_db import PaymentRequestDB, SentPayments,MsisdnValidation, WalletBalance, PaymentStatus, StatementHistory

# -------------------------
# App setup
# -------------------------
app = FastAPI(title="Relworx API for Uganda Mobile Money")

load_dotenv()

API_KEY = os.getenv("RELWORX_API_KEY")
BASE_URL = os.getenv("RELWORX_BASE_URL")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/vnd.relworx.v2"
}

# Create database tables
Base.metadata.create_all(bind=engine)

# -------------------------
# 1. Request Payment (Collection)
# -------------------------
@app.post("/request-payment")
def request_payment(request: RequestPayment, db: Session = Depends(get_db)):
    
    # Build payload for provider API
    payload = request.dict()
    customer_ref = generate_reference("CUST")
    payload["reference"] = generate_reference("REQ")


    #call Relworx API
    try:
        response = requests.post(f"{BASE_URL}/mobile-money/request-payment", json=payload, headers=HEADERS)
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    #Extract Internal-reference from provider on relworx

    internal_ref = data.get("internal_reference", payload["reference"]) or data.get("reference") or customer_ref
    


    # Save to database
    db_request = PaymentRequestDB(
        reference=payload["reference"],
        msisdn=request.msisdn,
        amount=request.amount,
        currency=request.currency,
        status=data.get("status", "pending"),
        response=data
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)

    # return both customer reference and internal reference 
    return {
        "success": True,
        "message": data.get("message", "Request payment in progress"),
        "customer_reference": payload["reference"],
    }

# -------------------------
# 2. Send Payment (Disbursement)
# -------------------------
@app.post("/send-payment")
def send_payment(request: SendPayment, db: Session = Depends(get_db)):
    payload = request.dict()
    payload["reference"] = generate_reference("SEND")

    try:
        response = requests.post(f"{BASE_URL}/mobile-money/send-payment", json=payload, headers=HEADERS)
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    # Save to database
    db_payment = SentPayments(
        reference=payload["reference"],
        msisdn=request.msisdn,
        amount=request.amount,
        currency=request.currency,
        status=data.get("status", "pending"),
        response=data
    )
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)

    if response.status_code not in [200, 201]:
        raise HTTPException(response.status_code, response.text)

    return data

# -------------------------
# 3. Validate MSISDN
# -------------------------
@app.post("/validate-msisdn")
def validate_msisdn(request: ValidateMsisdn, db: Session = Depends(get_db)):
    msisdn = request.msisdn.strip().replace(" ", "").replace("-", "")
    pattern = r"^(\+2567\d{8}|07\d{8})$"

     #save to databse
    db_validation = MsisdnValidation(
            msisdn=msisdn,
            is_valid="true",
            provider_response={"message": "Valid MSISDN format"}
        )
    db.add(db_validation)
    db.commit()
    db.refresh(db_validation)

    if re.fullmatch(pattern, msisdn):
        return {"valid": True, "msisdn": msisdn}

       
    else:
        return {"valid": False, "msisdn": msisdn, "message": "Invalid MSISDN format"}

# -------------------------
# 4. Check Wallet Balance
# -------------------------
@app.get("/wallet/check-balance")
def check_wallet_balance(
    account_no: str = Query(
        ..., 
        examples={"example": {"value": "RELB0C798FGHVCS"}}
    ),
    currency: str = Query(
        ..., 
        examples={"example": {"value": "UGX"}}
    ),
    db: Session = Depends(get_db)
):
    url = f"{BASE_URL}/mobile-money/check-wallet-balance"
    params = {"account_no": account_no, "currency": currency}

    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            print("Provider response:", e.response.text)
        raise HTTPException(status_code=502, detail=f"Network/provider error: {str(e)}")

    # 🔹 Extract balance safely
    balance = data.get("balance")

    # 🔹 Check if account exists in DB
    db_balance = db.query(WalletBalance).filter_by(account_no=account_no).first()

    if db_balance:
        # Update existing record
        db_balance.balance = balance
        db_balance.currency = currency
        db_balance.provider_response = data
    else:
        # Create new record
        db_balance = WalletBalance(
            account_no=account_no,
            currency=currency,
            balance=balance,
            provider_response=data
        )
        db.add(db_balance)

    db.commit()
    db.refresh(db_balance)

    return data

# -------------------------
# 5. Check Payment Request Status
# -------------------------
@app.get("/payment/check-request-status")
def get_all_transaction_status(
    internal_reference: str,
    account_no: str,
    db: Session = Depends(get_db)
):
    url = f"{BASE_URL}/mobile-money/check-request-status"
    params = {
        "internal_reference": internal_reference,
        "account_no": account_no
    }

    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    status = data.get("status")

    #. UPDATE main payment request
    payment = (
        db.query(PaymentRequestDB)
        .filter(PaymentRequestDB.reference == internal_reference)
        .first()
    )

    if payment:
        payment.status = status
        payment.response = data

    # insert into payment status table
    status_row = PaymentStatus(
        reference=internal_reference,
        status=status,
        provider_response=data
    )

    db.add(status_row)
    db.commit()

    return data

# -------------------------
# 6. List Transactions
# -------------------------
@app.get("/payment/list-transactions")
def list_transactions(
    account_no: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db)
):
    url = f"{BASE_URL}/payment-requests/transactions"
    params = {
        "account_no": account_no,
        "from_date": from_date,
        "to_date": to_date
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    #  SAVE EACH TRANSACTION
    for tx in data.get("transactions", []):
        tx_row = StatementHistory(
            reference=tx.get("customer_reference"),
            account_no=account_no,
            amount=tx.get("amount"),
            currency=tx.get("currency"),
            status=tx.get("status"),
            provider_response=tx
        )
        db.add(tx_row)

    db.commit()

    return data

# ----------------------------------------------------------------
# 7. Additional: Fetch DB Logs from the IDE for debugging/auditing
# -----------------------------------------------------------------
@app.get("/db/payment-requests")
def get_payment_requests(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(PaymentRequestDB).order_by(PaymentRequestDB.created_at.desc()).limit(limit).all()

@app.get("/db/sent-payments")
def get_sent_payments(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(SentPayments).order_by(SentPayments.created_at.desc()).limit(limit).all()


# -------------------------
# 8. Relworx Webhook Endpoint
# -------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

@app.post("/webhooks/relworx")
async def relworx_webhook(payload: RelworxWebhookPayload, db: Session = Depends(get_db)):
    """
    Webhook endpoint for Relworx payment status updates.
    -Triggered when a payment request changes from pending -> success/failed.
    - saves status, updatesPaymentRequestDB, and logs to StatementHistory for auditing.
    """

    # Duplicate protection: check if already processed
    existing = db.query(PaymentStatus).filter(PaymentStatus.reference == payload.customer_reference).first()
    if existing:
        logger.info(f"Webhook already processed for reference: {payload.customer_reference}")
        return {"message": "Webhook already processed"}

    # Save to PaymentStatus table
    status_row = PaymentStatus(
        reference=payload.customer_reference,
        status=payload.status,
        provider_response=payload.dict()
    )
    db.add(status_row)

    # Update PaymentRequestDB if exists
    payment = db.query(PaymentRequestDB).filter(PaymentRequestDB.reference == payload.customer_reference).first()
    if payment:
        payment.status = payload.status
        payment.response = payload.dict()
        db.add(payment)

    # Save to StatementHistory for auditing
    statement_row = StatementHistory(
        reference=payload.customer_reference,
        account_no=payload.msisdn,
        amount=payload.amount,
        currency=payload.currency,
        status={"status": payload.status},
        provider_response=payload.dict(), # saves the full webhook payload as a Json and will respond null
        statement_data={
            "internal_reference": payload.internal_reference,
            "completed_at": payload.completed_at
        }
    )
    db.add(statement_row)

    # Commit all changes
    db.commit()

    logger.info(f"Webhook processed successfully for reference: {payload.customer_reference}")

    # Must respond 200 OK for Relworx to stop retrying
    return {"message": "Webhook processed successfully"}
    
