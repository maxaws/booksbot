from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class Apporteur(Base):
    __tablename__ = "apporteurs"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(100), nullable=False)
    prenom = Column(String(100), nullable=False)
    email = Column(String(254), unique=True, index=True, nullable=False)
    telephone = Column(String(30), nullable=True)
    societe = Column(String(200), nullable=True)
    taux_commission = Column(Float, default=10.0)
    actif = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)

    opportunites = relationship("Opportunite", back_populates="apporteur")
    commissions = relationship("Commission", back_populates="apporteur")


class Opportunite(Base):
    __tablename__ = "opportunites"

    id = Column(Integer, primary_key=True, index=True)
    apporteur_id = Column(Integer, ForeignKey("apporteurs.id", ondelete="RESTRICT"), nullable=False)
    nom_prospect = Column(String(200), nullable=False)
    societe_prospect = Column(String(200), nullable=True)
    montant_estime = Column(Float, default=0.0)
    # nouveau | en_cours | gagne | perdu
    statut = Column(String(20), default="nouveau", nullable=False)
    description = Column(String(2000), nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_cloture = Column(DateTime, nullable=True)

    apporteur = relationship("Apporteur", back_populates="opportunites")
    commission = relationship("Commission", back_populates="opportunite", uselist=False)


class Commission(Base):
    __tablename__ = "commissions"

    id = Column(Integer, primary_key=True, index=True)
    opportunite_id = Column(Integer, ForeignKey("opportunites.id", ondelete="RESTRICT"), nullable=False, unique=True)
    apporteur_id = Column(Integer, ForeignKey("apporteurs.id", ondelete="RESTRICT"), nullable=False)
    montant = Column(Float, nullable=False)
    # en_attente | paye
    statut_paiement = Column(String(20), default="en_attente", nullable=False)
    date_calcul = Column(DateTime, default=datetime.utcnow)
    date_paiement = Column(DateTime, nullable=True)

    opportunite = relationship("Opportunite", back_populates="commission")
    apporteur = relationship("Apporteur", back_populates="commissions")
