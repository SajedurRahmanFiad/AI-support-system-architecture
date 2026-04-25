from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.api.deps import brand_token_header, platform_token_header
from app.api.schemas.products import ProductImageUpdate
from app.database import get_db
from app.services.brand_service import require_brand_access
from app.services.product_recognition import ProductRecognizer
from app.services.storage import save_upload
from app.config import get_settings
import json

router = APIRouter(prefix="/v1/products")


def _resolve_storage_path(storage_path: str) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path
    return get_settings().upload_path / path


def _serialize_product_image(product_img: models.ProductImage) -> dict[str, Any]:
    return {
        "id": product_img.id,
        "product_name": product_img.product_name,
        "category": product_img.product_category,
        "storage_path": product_img.storage_path,
        "metadata": product_img.product_metadata or {},
        "created_at": product_img.created_at,
        "updated_at": product_img.updated_at,
    }


@router.post("/images/add")
def add_product_image(
    product_name: str = Form(...),
    category: str = Form("general"),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    brand_id: int = Form(...),
    metadata: str = Form("{}"),  # JSON string
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, Any]:
    """Upload a product image for recognition training"""
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    uploads: list[UploadFile] = []
    if file is not None:
        uploads.append(file)
    uploads.extend(files or [])
    if not uploads:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image file is required.")

    try:
        metadata_dict = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid metadata JSON")

    recognizer = ProductRecognizer(db, brand_id)
    created_images: list[models.ProductImage] = []
    for upload in uploads:
        if not ((upload.content_type or "").startswith("image/")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed.")
        try:
            image_data = upload.file.read()
            upload.file.seek(0)
            storage_path, mime_type = save_upload(brand_id, upload)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not save image: {exc}")

        try:
            product_img = recognizer.add_product_image(
                product_name=product_name,
                category=category,
                storage_path=storage_path,
                mime_type=mime_type,
                image_data=image_data,
                metadata=metadata_dict,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        created_images.append(product_img)

    first_image = created_images[0]

    return {
        "status": "Product images added for visual recognition",
        "product_image_id": first_image.id,
        "product_image_ids": [image.id for image in created_images],
        "product_name": product_name,
        "category": category,
        "count": len(created_images),
        "product_images": [_serialize_product_image(image) for image in created_images],
        "storage_path": first_image.storage_path,
        "visual_summary": (first_image.product_metadata or {}).get("visual_summary"),
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

    try:
        recognizer = ProductRecognizer(db, brand_id)
        result = recognizer.recognize_product_from_image(
            image_data=image_data,
            mime_type=file.content_type or "image/jpeg",
            customer_text=customer_text,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Product recognition is temporarily unavailable. Please try again.",
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
    product_groups = recognizer.get_product_groups()

    return {
        "brand_id": brand_id,
        "product_images": images,
        "product_groups": product_groups,
        "count": len(images),
        "group_count": len(product_groups),
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


@router.delete("/groups/{product_image_id}")
def delete_product_group(
    product_image_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, str]:
    """Delete a product group and every image stored under it."""
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)

    recognizer = ProductRecognizer(db, brand_id)
    success = recognizer.delete_product_group(product_image_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return {"status": "Product deleted"}


@router.patch("/images/{product_image_id}")
def update_product_image(
    product_image_id: int,
    payload: ProductImageUpdate,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, Any]:
    product_img = db.get(models.ProductImage, product_image_id)
    if not product_img:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product image not found")
    require_brand_access(db, product_img.brand_id, brand_token, platform_token, get_settings().platform_api_token)

    data = payload.model_dump(exclude_unset=True)
    if "product_name" in data:
        product_img.product_name = data["product_name"]
    if "category" in data:
        product_img.product_category = data["category"]
    if "metadata" in data:
        product_img.product_metadata = data["metadata"]
    db.add(product_img)
    db.commit()
    db.refresh(product_img)
    return _serialize_product_image(product_img)


@router.get("/images/{product_image_id}/download")
def download_product_image(
    product_image_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> FileResponse:
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    product_img = db.get(models.ProductImage, product_image_id)
    if not product_img or product_img.brand_id != brand_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product image not found")
    file_path = _resolve_storage_path(product_img.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")
    return FileResponse(
        path=file_path,
        media_type=(product_img.product_metadata or {}).get("mime_type", "image/jpeg"),
        filename=file_path.name,
    )
