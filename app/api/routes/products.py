from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.api.deps import brand_token_header, platform_token_header
from app.database import get_db
from app.services.brand_service import require_brand_access
from app.services.product_recognition import ProductRecognizer
from app.services.storage import save_upload
from app.config import get_settings
import json

router = APIRouter(prefix="/v1/products")


@router.post("/images/add")
def add_product_image(
    product_name: str = Form(...),
    category: str = Form("general"),
    file: UploadFile = File(...),
    brand_id: int = Form(...),
    metadata: str = Form("{}"),  # JSON string
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, Any]:
    """Upload a product image for recognition training"""
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed.")

    try:
        metadata_dict = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid metadata JSON")

    try:
        image_data = file.file.read()
        file.file.seek(0)
        storage_path, mime_type = save_upload(brand_id, file)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not save image: {e}")

    # Add to database
    try:
        recognizer = ProductRecognizer(db, brand_id)
        product_img = recognizer.add_product_image(
            product_name=product_name,
            category=category,
            storage_path=storage_path,
            mime_type=mime_type,
            image_data=image_data,
            metadata=metadata_dict,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "status": "Product image added for visual recognition",
        "product_image_id": product_img.id,
        "product_name": product_name,
        "category": category,
        "storage_path": storage_path,
        "visual_summary": (product_img.product_metadata or {}).get("visual_summary"),
    }


@router.post("/recognize")
def recognize_product(
    file: UploadFile = File(...),
    brand_id: int = Form(...),
    customer_text: str = Form(""),
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, Any]:
    """Recognize product from a customer-sent image"""
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed.")

    try:
        image_data = file.file.read()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not read image: {e}")

    recognizer = ProductRecognizer(db, brand_id)
    result = recognizer.recognize_product_from_image(
        image_data=image_data,
        mime_type=file.content_type or "image/jpeg",
        customer_text=customer_text,
    )

    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

    return result


@router.get("/images")
def get_product_images(
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, Any]:
    """Get all product images for a brand"""
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)

    recognizer = ProductRecognizer(db, brand_id)
    images = recognizer.get_product_images()

    return {
        "brand_id": brand_id,
        "product_images": images,
        "count": len(images)
    }


@router.delete("/images/{product_image_id}")
def delete_product_image(
    product_image_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, str]:
    """Delete a product image"""
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)

    recognizer = ProductRecognizer(db, brand_id)
    success = recognizer.delete_product_image(product_image_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product image not found")

    return {"status": "Product image deleted"}
