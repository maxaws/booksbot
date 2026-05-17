from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Commission, Opportunite
from schemas import CommissionOut

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)


def _to_out(c: Commission) -> CommissionOut:
    return CommissionOut(
        id=c.id,
        opportunite_id=c.opportunite_id,
        apporteur_id=c.apporteur_id,
        montant=c.montant,
        statut_paiement=c.statut_paiement,
        date_calcul=c.date_calcul,
        date_paiement=c.date_paiement,
        apporteur_nom=c.apporteur.nom if c.apporteur else "",
        apporteur_prenom=c.apporteur.prenom if c.apporteur else "",
        prospect_nom=c.opportunite.nom_prospect if c.opportunite else "",
        prospect_societe=c.opportunite.societe_prospect if c.opportunite else None,
        montant_affaire=c.opportunite.montant_estime if c.opportunite else 0.0,
    )


@router.get("/", response_model=list[CommissionOut])
def list_commissions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    commissions = (
        db.query(Commission)
        .join(Opportunite)
        .order_by(Commission.date_calcul.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_out(c) for c in commissions]


@router.put("/{commission_id}/marquer-paye", response_model=CommissionOut)
@_limiter.limit("20/minute")
def marquer_paye(
    request: Request,
    commission_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    commission = db.query(Commission).filter(Commission.id == commission_id).first()
    if not commission:
        raise HTTPException(status_code=404, detail="Commission introuvable")
    if commission.statut_paiement == "paye":
        raise HTTPException(status_code=400, detail="Commission déjà marquée payée")
    commission.statut_paiement = "paye"
    commission.date_paiement = datetime.utcnow()
    db.commit()
    db.refresh(commission)
    return _to_out(commission)
