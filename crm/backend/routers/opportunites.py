from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Apporteur, Commission, Opportunite
from schemas import (
    OpportuniteCreate,
    OpportuniteOut,
    OpportuniteUpdate,
    TRANSITIONS_AUTORISEES,
)

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)

TERMINAL_STATUTS = {"gagne", "perdu"}


def _to_out(opp: Opportunite) -> OpportuniteOut:
    return OpportuniteOut(
        id=opp.id,
        apporteur_id=opp.apporteur_id,
        nom_prospect=opp.nom_prospect,
        societe_prospect=opp.societe_prospect,
        montant_estime=opp.montant_estime,
        statut=opp.statut,
        description=opp.description,
        date_creation=opp.date_creation,
        date_cloture=opp.date_cloture,
        apporteur_nom=opp.apporteur.nom if opp.apporteur else "",
        apporteur_prenom=opp.apporteur.prenom if opp.apporteur else "",
    )


def _sync_commission(opp: Opportunite, db: Session):
    if opp.statut == "gagne":
        if not opp.apporteur:
            raise HTTPException(status_code=422, detail="Apporteur introuvable pour le calcul de commission")
        taux = opp.apporteur.taux_commission
        montant = round(opp.montant_estime * taux / 100, 2)
        if opp.commission:
            opp.commission.montant = montant
        else:
            db.add(Commission(
                opportunite_id=opp.id,
                apporteur_id=opp.apporteur_id,
                montant=montant,
            ))
        if not opp.date_cloture:
            opp.date_cloture = datetime.utcnow()

    elif opp.statut == "perdu":
        if opp.commission and opp.commission.statut_paiement == "en_attente":
            db.delete(opp.commission)
        if not opp.date_cloture:
            opp.date_cloture = datetime.utcnow()

    else:
        # non-terminal — retirer la commission en attente si elle existe
        if opp.commission and opp.commission.statut_paiement == "en_attente":
            db.delete(opp.commission)
        opp.date_cloture = None


@router.get("/", response_model=list[OpportuniteOut])
def list_opportunites(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    opps = (
        db.query(Opportunite)
        .join(Apporteur)
        .order_by(Opportunite.date_creation.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_out(o) for o in opps]


@router.post("/", response_model=OpportuniteOut, status_code=201)
@_limiter.limit("30/minute")
def create_opportunite(
    request: Request,
    payload: OpportuniteCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
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
def get_opportunite(
    opp_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    opp = db.query(Opportunite).filter(Opportunite.id == opp_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunité introuvable")
    return _to_out(opp)


@router.put("/{opp_id}", response_model=OpportuniteOut)
def update_opportunite(
    opp_id: int,
    payload: OpportuniteUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    opp = db.query(Opportunite).filter(Opportunite.id == opp_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunité introuvable")

    # Validate status transition
    new_statut = payload.statut
    if new_statut and new_statut != opp.statut:
        allowed = TRANSITIONS_AUTORISEES.get(opp.statut, set())
        if new_statut not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transition de statut invalide : '{opp.statut}' → '{new_statut}'. "
                       f"Statuts autorisés depuis '{opp.statut}' : {sorted(allowed)}",
            )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opp, field, value)
    db.flush()
    db.refresh(opp)
    _sync_commission(opp, db)
    db.commit()
    db.refresh(opp)
    return _to_out(opp)


@router.delete("/{opp_id}", status_code=204)
def delete_opportunite(
    opp_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
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
