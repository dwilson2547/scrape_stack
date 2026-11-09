from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Bucket, Domain
from ..schemas import BucketCreate, BucketDetail, BucketDomainAdd, BucketRead, BucketUpdate

router = APIRouter(prefix="/buckets", tags=["buckets"])


@router.get("", response_model=list[BucketRead])
def list_buckets(db: Session = Depends(get_db)):
    return db.query(Bucket).order_by(Bucket.name).all()


@router.post("", response_model=BucketRead, status_code=201)
def create_bucket(body: BucketCreate, db: Session = Depends(get_db)):
    if db.query(Bucket).filter_by(name=body.name).first():
        raise HTTPException(400, f"bucket {body.name!r} already exists")
    bucket = Bucket(**body.model_dump())
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return bucket


@router.get("/{bucket_id}", response_model=BucketDetail)
def get_bucket(bucket_id: int, db: Session = Depends(get_db)):
    bucket = db.get(Bucket, bucket_id)
    if not bucket:
        raise HTTPException(404, "bucket not found")
    return bucket


@router.patch("/{bucket_id}", response_model=BucketRead)
def update_bucket(bucket_id: int, body: BucketUpdate, db: Session = Depends(get_db)):
    bucket = db.get(Bucket, bucket_id)
    if not bucket:
        raise HTTPException(404, "bucket not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bucket, field, value)
    db.commit()
    db.refresh(bucket)
    return bucket


@router.delete("/{bucket_id}", status_code=204)
def delete_bucket(bucket_id: int, db: Session = Depends(get_db)):
    bucket = db.get(Bucket, bucket_id)
    if not bucket:
        raise HTTPException(404, "bucket not found")
    db.delete(bucket)
    db.commit()


@router.post("/{bucket_id}/domains", status_code=204)
def add_domain_to_bucket(bucket_id: int, body: BucketDomainAdd, db: Session = Depends(get_db)):
    if not db.get(Bucket, bucket_id):
        raise HTTPException(404, "bucket not found")
    domain = db.get(Domain, body.domain_id)
    if not domain:
        raise HTTPException(404, "domain not found")
    domain.bucket_id = bucket_id
    db.commit()


@router.delete("/{bucket_id}/domains/{domain_id}", status_code=204)
def remove_domain_from_bucket(bucket_id: int, domain_id: int, db: Session = Depends(get_db)):
    domain = db.get(Domain, domain_id)
    if not domain or domain.bucket_id != bucket_id:
        raise HTTPException(404, "domain not in this bucket")
    domain.bucket_id = None
    db.commit()
