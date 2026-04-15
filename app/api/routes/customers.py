from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.customers import CustomerFactOut, CustomerOut

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
