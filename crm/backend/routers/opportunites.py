from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Apporteur, Commission, Opportunite
from schemas import OpportuniteCreate, OpportuniteOut, OpportuniteUpdate

router = APIRouter()


def _to_out(opp: Opportunite) -> OpportuniteOut:
    data = {
        "id": opp.id,
        "apporteur_id": opp.apporteur_id,
        "nom_prospect": opp.nom_prospect,
        "societe_prospect": opp.societe_prospect,
        "montant_estime": opp.montant_estime,
        "statut": opp.statut,
        "description": opp.description,
        "date_creation": opp.date_creation,
        "date_cloture": opp.date_cloture,
        "apporteur_nom": opp.apporteur.nom if opp.apporteur else "",
        "apporteur_prenom": opp.apporteur.prenom if opp.apporteur else "",
    }
    return OpportuniteOut(**data)


def _sync_commission(opp: Opportunite, db: Session):
    if opp.statut == "gagne":
        taux = opp.apporteur.taux_commission if opp.apporteur else 0.0
        montant = round(opp.montant_estime * taux / 100, 2)
        if opp.commission:
            opp.commission.montant = montant
        else:
            commission = Commission(
                opportunite_id=opp.id,
                apporteur_id=opp.apporteur_id,
                montant=montant,
            )
            db.add(commission)
        if not opp.date_cloture:
            opp.date_cloture = datetime.utcnow()
    else:
        if opp.commission and opp.commission.statut_paiement == "en_attente":
            db.delete(opp.commission)
        opp.date_cloture = None if opp.statut not in ("perdu",) else opp.date_cloture
        if opp.statut == "perdu" and not opp.date_cloture:
            opp.date_cloture = datetime.utcnow()


@router.get("/", response_model=list[OpportuniteOut])
def list_opportunites(db: Session = Depends(get_db)):
    opps = (
        db.query(Opportunite)
        .join(Apporteur)
        .order_by(Opportunite.date_creation.desc())
        .all()
    )
    return [_to_out(o) for o in opps]


@router.post("/", response_model=OpportuniteOut, status_code=201)
def create_opportunite(payload: OpportuniteCreate, db: Session = Depends(get_db)):
    apporteur = db.query(Apporteur).filter(Apporteur.id == payload.apporteur_id).first()
    if not apporteur:
        raise HTTPException(status_code=404, detail="Apporteur introuvable")
    opp = Opportunite(**payload.model_dump())
    db.add(opp)
    db.flush()
    db.refresh(opp)
    _sync_commission(opp, db)
    db.commit()
    db.refresh(opp)
    return _to_out(opp)


@router.get("/{opp_id}", response_model=OpportuniteOut)
def get_opportunite(opp_id: int, db: Session = Depends(get_db)):
    opp = db.query(Opportunite).filter(Opportunite.id == opp_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunité introuvable")
    return _to_out(opp)


@router.put("/{opp_id}", response_model=OpportuniteOut)
def update_opportunite(
    opp_id: int, payload: OpportuniteUpdate, db: Session = Depends(get_db)
):
    opp = db.query(Opportunite).filter(Opportunite.id == opp_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunité introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opp, field, value)
    db.flush()
    db.refresh(opp)
    _sync_commission(opp, db)
    db.commit()
    db.refresh(opp)
    return _to_out(opp)


@router.delete("/{opp_id}", status_code=204)
def delete_opportunite(opp_id: int, db: Session = Depends(get_db)):
    opp = db.query(Opportunite).filter(Opportunite.id == opp_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunité introuvable")
    if opp.commission and opp.commission.statut_paiement == "paye":
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer : une commission déjà payée est liée",
        )
    if opp.commission:
        db.delete(opp.commission)
    db.delete(opp)
    db.commit()
