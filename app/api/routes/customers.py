from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.customers import (
    CustomerFactCreate,
    CustomerFactOut,
    CustomerFactUpdate,
    CustomerOut,
    CustomerUpdate,
)

router = APIRouter(prefix="/v1/customers", dependencies=[Depends(require_platform_access)])


@router.get("", response_model=list[CustomerOut])
def list_customers(brand_id: int, db: DbSession) -> list[models.Customer]:
    return list(
        db.scalars(
            select(models.Customer)
            .where(models.Customer.brand_id == brand_id)
            .order_by(models.Customer.updated_at.desc())
        )
    )


@router.get("/{customer_id}")
def get_customer(customer_id: int, db: DbSession) -> dict:
    customer = db.scalar(
        select(models.Customer)
        .options(joinedload(models.Customer.facts))
        .where(models.Customer.id == customer_id)
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return {
        "customer": CustomerOut.model_validate(customer).model_dump(),
        "facts": [CustomerFactOut.model_validate(item).model_dump() for item in customer.facts],
    }


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate, db: DbSession) -> models.Customer:
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "profile":
            customer.profile_json = value
        else:
            setattr(customer, field, value)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.post("/{customer_id}/facts", response_model=CustomerFactOut)
def create_customer_fact(customer_id: int, payload: CustomerFactCreate, db: DbSession) -> models.CustomerFact:
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    row = models.CustomerFact(
        brand_id=customer.brand_id,
        customer_id=customer.id,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{customer_id}/facts/{fact_id}", response_model=CustomerFactOut)
def update_customer_fact(
    customer_id: int,
    fact_id: int,
    payload: CustomerFactUpdate,
    db: DbSession,
) -> models.CustomerFact:
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    fact = db.get(models.CustomerFact, fact_id)
    if not fact or fact.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer fact not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(fact, field, value)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


@router.delete("/{customer_id}/facts/{fact_id}")
def delete_customer_fact(customer_id: int, fact_id: int, db: DbSession) -> dict[str, str]:
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    fact = db.get(models.CustomerFact, fact_id)
    if not fact or fact.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer fact not found.")
    db.delete(fact)
    db.commit()
    return {"status": "deleted"}
