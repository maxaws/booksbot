from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Apporteur, Commission, Opportunite
from schemas import ApporteurCreate, ApporteurDetail, ApporteurOut, ApporteurUpdate

router = APIRouter()


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
def list_apporteurs(db: Session = Depends(get_db)):
    apporteurs = db.query(Apporteur).order_by(Apporteur.nom).all()
    return [_enrich(a, db) for a in apporteurs]


@router.post("/", response_model=ApporteurOut, status_code=201)
def create_apporteur(payload: ApporteurCreate, db: Session = Depends(get_db)):
    if db.query(Apporteur).filter(Apporteur.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    apporteur = Apporteur(**payload.model_dump())
    db.add(apporteur)
    db.commit()
    db.refresh(apporteur)
    return apporteur


@router.get("/{apporteur_id}", response_model=ApporteurDetail)
def get_apporteur(apporteur_id: int, db: Session = Depends(get_db)):
    apporteur = db.query(Apporteur).filter(Apporteur.id == apporteur_id).first()
    if not apporteur:
        raise HTTPException(status_code=404, detail="Apporteur introuvable")
    return _enrich(apporteur, db)


@router.put("/{apporteur_id}", response_model=ApporteurOut)
def update_apporteur(
    apporteur_id: int, payload: ApporteurUpdate, db: Session = Depends(get_db)
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
def delete_apporteur(apporteur_id: int, db: Session = Depends(get_db)):
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
