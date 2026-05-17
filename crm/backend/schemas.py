from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Apporteur ────────────────────────────────────────────────────────────────

class ApporteurBase(BaseModel):
    nom: str
    prenom: str
    email: str
    telephone: Optional[str] = None
    societe: Optional[str] = None
    taux_commission: float = 10.0
    actif: bool = True


class ApporteurCreate(ApporteurBase):
    pass


class ApporteurUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    societe: Optional[str] = None
    taux_commission: Optional[float] = None
    actif: Optional[bool] = None


class ApporteurOut(ApporteurBase):
    id: int
    date_creation: datetime

    model_config = {"from_attributes": True}


class ApporteurDetail(ApporteurOut):
    nombre_opportunites: int = 0
    ca_total: float = 0.0


# ── Opportunite ───────────────────────────────────────────────────────────────

class OpportuniteBase(BaseModel):
    apporteur_id: int
    nom_prospect: str
    societe_prospect: Optional[str] = None
    montant_estime: float = 0.0
    statut: str = "nouveau"
    description: Optional[str] = None


class OpportuniteCreate(OpportuniteBase):
    pass


class OpportuniteUpdate(BaseModel):
    nom_prospect: Optional[str] = None
    societe_prospect: Optional[str] = None
    montant_estime: Optional[float] = None
    statut: Optional[str] = None
    description: Optional[str] = None
    apporteur_id: Optional[int] = None


class OpportuniteOut(OpportuniteBase):
    id: int
    date_creation: datetime
    date_cloture: Optional[datetime] = None
    apporteur_nom: str = ""
    apporteur_prenom: str = ""

    model_config = {"from_attributes": True}


# ── Commission ────────────────────────────────────────────────────────────────

class CommissionOut(BaseModel):
    id: int
    opportunite_id: int
    apporteur_id: int
    montant: float
    statut_paiement: str
    date_calcul: datetime
    date_paiement: Optional[datetime] = None
    apporteur_nom: str = ""
    apporteur_prenom: str = ""
    prospect_nom: str = ""
    prospect_societe: Optional[str] = None
    montant_affaire: float = 0.0

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class TopApporteur(BaseModel):
    id: int
    nom: str
    prenom: str
    ca_total: float
    nb_affaires: int


class DashboardStats(BaseModel):
    total_apporteurs: int
    opportunites_en_cours: int
    ca_gagne: float
    commissions_dues: float
    top_apporteurs: list[TopApporteur]
