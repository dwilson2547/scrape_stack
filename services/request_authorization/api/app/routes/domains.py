from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Domain
from ..schemas import DomainCreate, DomainRead, DomainUpdate

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("", response_model=list[DomainRead])
def list_domains(db: Session = Depends(get_db)):
    return db.query(Domain).order_by(Domain.hostname).all()


@router.post("", response_model=DomainRead, status_code=201)
def create_domain(body: DomainCreate, db: Session = Depends(get_db)):
    if db.query(Domain).filter_by(hostname=body.hostname).first():
        raise HTTPException(400, f"domain {body.hostname!r} already exists")
    domain = Domain(**body.model_dump())
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


@router.get("/{hostname}", response_model=DomainRead)
def get_domain(hostname: str, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter_by(hostname=hostname).first()
    if not domain:
        raise HTTPException(404, "domain not found")
    return domain


@router.patch("/{hostname}", response_model=DomainRead)
def update_domain(hostname: str, body: DomainUpdate, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter_by(hostname=hostname).first()
    if not domain:
        raise HTTPException(404, "domain not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(domain, field, value)
    db.commit()
    db.refresh(domain)
    return domain


@router.delete("/{hostname}", status_code=204)
def delete_domain(hostname: str, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter_by(hostname=hostname).first()
    if not domain:
        raise HTTPException(404, "domain not found")
    db.delete(domain)
    db.commit()
