from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth import get_current_user
from database import get_db
from models import Apporteur, Opportunite
from schemas import ApporteurCreate, ApporteurDetail, ApporteurOut, ApporteurUpdate

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)


def _enrich(apporteur: Apporteur, db: Session) -> ApporteurDetail:
    nb = db.query(func.count(Opportunite.id)).filter(
        Opportunite.apporteur_id == apporteur.id
    ).scalar() or 0
    ca = db.query(func.sum(Opportunite.montant_estime)).filter(
        Opportunite.apporteur_id == apporteur.id,
        Opportunite.statut == "gagne",
    ).scalar() or 0.0
    return ApporteurDetail(
        **ApporteurOut.model_validate(apporteur).model_dump(),
        nombre_opportunites=nb,
        ca_total=ca,
    )


@router.get("/", response_model=list[ApporteurDetail])
def list_apporteurs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    apporteurs = (
        db.query(Apporteur).order_by(Apporteur.nom).offset(skip).limit(limit).all()
    )
    return [_enrich(a, db) for a in apporteurs]


@router.post("/", response_model=ApporteurOut, status_code=201)
@_limiter.limit("30/minute")
def create_apporteur(
    request: Request,
    payload: ApporteurCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    if db.query(Apporteur).filter(Apporteur.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    apporteur = Apporteur(**payload.model_dump())
    db.add(apporteur)
    db.commit()
    db.refresh(apporteur)
    return apporteur


@router.get("/{apporteur_id}", response_model=ApporteurDetail)
def get_apporteur(
    apporteur_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    apporteur = db.query(Apporteur).filter(Apporteur.id == apporteur_id).first()
    if not apporteur:
        raise HTTPException(status_code=404, detail="Apporteur introuvable")
    return _enrich(apporteur, db)


@router.put("/{apporteur_id}", response_model=ApporteurOut)
def update_apporteur(
    apporteur_id: int,
    payload: ApporteurUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    apporteur = db.query(Apporteur).filter(Apporteur.id == apporteur_id).first()
    if not apporteur:
        raise HTTPException(status_code=404, detail="Apporteur introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(apporteur, field, value)
    db.commit()
    db.refresh(apporteur)
    return apporteur


@router.delete("/{apporteur_id}", status_code=204)
def delete_apporteur(
    apporteur_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    apporteur = db.query(Apporteur).filter(Apporteur.id == apporteur_id).first()
    if not apporteur:
        raise HTTPException(status_code=404, detail="Apporteur introuvable")
    if db.query(Opportunite).filter(Opportunite.apporteur_id == apporteur_id).first():
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer : des opportunités sont liées à cet apporteur",
        )
    db.delete(apporteur)
    db.commit()
