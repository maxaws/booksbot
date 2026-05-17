from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Apporteur, Commission, Opportunite
from schemas import DashboardStats, TopApporteur

router = APIRouter()


@router.get("/", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    total_apporteurs = (
        db.query(func.count(Apporteur.id)).filter(Apporteur.actif == True).scalar() or 0
    )

    opportunites_en_cours = (
        db.query(func.count(Opportunite.id))
        .filter(Opportunite.statut.in_(["nouveau", "en_cours"]))
        .scalar() or 0
    )

    ca_gagne = (
        db.query(func.sum(Opportunite.montant_estime))
        .filter(Opportunite.statut == "gagne")
        .scalar() or 0.0
    )

    commissions_dues = (
        db.query(func.sum(Commission.montant))
        .filter(Commission.statut_paiement == "en_attente")
        .scalar() or 0.0
    )

    top_raw = (
        db.query(
            Apporteur.id,
            Apporteur.nom,
            Apporteur.prenom,
            func.sum(Opportunite.montant_estime).label("ca_total"),
            func.count(Opportunite.id).label("nb_affaires"),
        )
        .join(Opportunite, Opportunite.apporteur_id == Apporteur.id)
        .filter(Opportunite.statut == "gagne")
        .group_by(Apporteur.id)
        .order_by(func.sum(Opportunite.montant_estime).desc())
        .limit(5)
        .all()
    )

    top_apporteurs = [
        TopApporteur(
            id=row.id,
            nom=row.nom,
            prenom=row.prenom,
            ca_total=row.ca_total or 0.0,
            nb_affaires=row.nb_affaires or 0,
        )
        for row in top_raw
    ]

    return DashboardStats(
        total_apporteurs=total_apporteurs,
        opportunites_en_cours=opportunites_en_cours,
        ca_gagne=ca_gagne,
        commissions_dues=commissions_dues,
        top_apporteurs=top_apporteurs,
    )
