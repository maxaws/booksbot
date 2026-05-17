from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class Apporteur(Base):
    __tablename__ = "apporteurs"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String, nullable=False)
    prenom = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    telephone = Column(String, nullable=True)
    societe = Column(String, nullable=True)
    taux_commission = Column(Float, default=10.0)
    actif = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)

    opportunites = relationship("Opportunite", back_populates="apporteur")
    commissions = relationship("Commission", back_populates="apporteur")


class Opportunite(Base):
    __tablename__ = "opportunites"

    id = Column(Integer, primary_key=True, index=True)
    apporteur_id = Column(Integer, ForeignKey("apporteurs.id"), nullable=False)
    nom_prospect = Column(String, nullable=False)
    societe_prospect = Column(String, nullable=True)
    montant_estime = Column(Float, default=0.0)
    # nouveau | en_cours | gagne | perdu
    statut = Column(String, default="nouveau", nullable=False)
    description = Column(String, nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_cloture = Column(DateTime, nullable=True)

    apporteur = relationship("Apporteur", back_populates="opportunites")
    commission = relationship("Commission", back_populates="opportunite", uselist=False)


class Commission(Base):
    __tablename__ = "commissions"

    id = Column(Integer, primary_key=True, index=True)
    opportunite_id = Column(Integer, ForeignKey("opportunites.id"), nullable=False, unique=True)
    apporteur_id = Column(Integer, ForeignKey("apporteurs.id"), nullable=False)
    montant = Column(Float, nullable=False)
    # en_attente | paye
    statut_paiement = Column(String, default="en_attente", nullable=False)
    date_calcul = Column(DateTime, default=datetime.utcnow)
    date_paiement = Column(DateTime, nullable=True)

    opportunite = relationship("Opportunite", back_populates="commission")
    apporteur = relationship("Apporteur", back_populates="commissions")
