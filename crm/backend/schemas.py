from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

# ── Apporteur ────────────────────────────────────────────────────────────────

class ApporteurBase(BaseModel):
    nom: Annotated[str, Field(min_length=1, max_length=100)]
    prenom: Annotated[str, Field(min_length=1, max_length=100)]
    email: EmailStr
    telephone: Annotated[Optional[str], Field(max_length=30)] = None
    societe: Annotated[Optional[str], Field(max_length=200)] = None
    taux_commission: Annotated[float, Field(ge=0.0, le=100.0)] = 10.0
    actif: bool = True


class ApporteurCreate(ApporteurBase):
    pass


class ApporteurUpdate(BaseModel):
    nom: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    prenom: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    email: Optional[EmailStr] = None
    telephone: Annotated[Optional[str], Field(max_length=30)] = None
    societe: Annotated[Optional[str], Field(max_length=200)] = None
    taux_commission: Annotated[Optional[float], Field(ge=0.0, le=100.0)] = None
    actif: Optional[bool] = None


class ApporteurOut(ApporteurBase):
    id: int
    date_creation: datetime

    model_config = {"from_attributes": True}


class ApporteurDetail(ApporteurOut):
    nombre_opportunites: int = 0
    ca_total: float = 0.0


# ── Opportunite ───────────────────────────────────────────────────────────────

StatutOpportunite = Literal["nouveau", "en_cours", "gagne", "perdu"]

# Transitions autorisées — on interdit la rétrogradation depuis un statut terminal
TRANSITIONS_AUTORISEES: dict[str, set[str]] = {
    "nouveau":  {"nouveau", "en_cours", "gagne", "perdu"},
    "en_cours": {"en_cours", "gagne", "perdu"},
    "gagne":    {"gagne"},   # terminal — commission potentiellement payée
    "perdu":    {"perdu"},   # terminal
}


class OpportuniteBase(BaseModel):
    apporteur_id: int
    nom_prospect: Annotated[str, Field(min_length=1, max_length=200)]
    societe_prospect: Annotated[Optional[str], Field(max_length=200)] = None
    montant_estime: Annotated[float, Field(ge=0.0)] = 0.0
    statut: StatutOpportunite = "nouveau"
    description: Annotated[Optional[str], Field(max_length=2000)] = None


class OpportuniteCreate(OpportuniteBase):
    pass


class OpportuniteUpdate(BaseModel):
    nom_prospect: Annotated[Optional[str], Field(min_length=1, max_length=200)] = None
    societe_prospect: Annotated[Optional[str], Field(max_length=200)] = None
    montant_estime: Annotated[Optional[float], Field(ge=0.0)] = None
    statut: Optional[StatutOpportunite] = None
    description: Annotated[Optional[str], Field(max_length=2000)] = None
    apporteur_id: Optional[int] = None


class OpportuniteOut(OpportuniteBase):
    id: int
    date_creation: datetime
    date_cloture: Optional[datetime] = None
    apporteur_nom: str = ""
    apporteur_prenom: str = ""

    model_config = {"from_attributes": True}


# ── Commission ────────────────────────────────────────────────────────────────

StatutPaiement = Literal["en_attente", "paye"]


class CommissionOut(BaseModel):
    id: int
    opportunite_id: int
    apporteur_id: int
    montant: float
    statut_paiement: StatutPaiement
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
