"""Multi-tank blending keeps reservation, formula and judgment evidence off the base tables."""
from decimal import Decimal
from sqlalchemy import String,Numeric,Float,ForeignKey,JSON,Integer,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
class BlendPlan(Base):
    __tablename__='blend_plans'
    __table_args__=(CheckConstraint('liters > 0'),CheckConstraint("grade IN ('VLSFO','MGO')"),CheckConstraint("state IN ('candidates','reserved','pending_retest','released','completed','cancelled')"))
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(70),unique=True)
    grade:Mapped[str]=mapped_column(String(20))
    liters:Mapped[Decimal]=mapped_column(Numeric(14,3))
    vessel:Mapped[str]=mapped_column(String(120))
    state:Mapped[str]=mapped_column(String(20),default='candidates')
    selected_candidate_id:Mapped[int|None]=mapped_column(Integer,nullable=True)
    line_id:Mapped[int|None]=mapped_column(ForeignKey('fuel_lines.id'),nullable=True)
    berth_id:Mapped[int|None]=mapped_column(ForeignKey('berths.id'),nullable=True)
    starts_at:Mapped[str]=mapped_column(String(40),default='')
    ends_at:Mapped[str]=mapped_column(String(40),default='')
    draft:Mapped[Decimal|None]=mapped_column(Numeric(8,3),nullable=True)
    retest_density:Mapped[Decimal|None]=mapped_column(Numeric(10,3),nullable=True)
    retest_note:Mapped[str]=mapped_column(String(2000),default='')
    retest_by:Mapped[str]=mapped_column(String(120),default='')
    released_by:Mapped[str]=mapped_column(String(120),default='')
    cancelled_by:Mapped[str]=mapped_column(String(120),default='')
    completed_note:Mapped[str]=mapped_column(String(600),default='')
    judgment:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    release_snapshot:Mapped[dict|None]=mapped_column(JSON,nullable=True)
class BlendCandidate(Base):
    __tablename__='blend_candidates'
    __table_args__=(CheckConstraint("verdict IN ('ok','low_likelihood')"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('blend_plans.id'))
    components:Mapped[list]=mapped_column(JSON)
    mix_density:Mapped[Decimal]=mapped_column(Numeric(10,3))
    mix_viscosity:Mapped[Decimal]=mapped_column(Numeric(10,3))
    mix_sulfur:Mapped[Decimal]=mapped_column(Numeric(7,4))
    score:Mapped[float]=mapped_column(Float)
    threshold:Mapped[float]=mapped_column(Float)
    verdict:Mapped[str]=mapped_column(String(20))
    rank:Mapped[int]=mapped_column(Integer)
class BlendComponent(Base):
    __tablename__='blend_components'
    __table_args__=(CheckConstraint('liters > 0'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('blend_plans.id'))
    tank_id:Mapped[int]=mapped_column(ForeignKey('tanks.id'))
    sample_id:Mapped[int]=mapped_column(ForeignKey('fuel_samples.id'))
    liters:Mapped[Decimal]=mapped_column(Numeric(14,3))
    ratio:Mapped[Decimal]=mapped_column(Numeric(8,6))
    density_snapshot:Mapped[Decimal]=mapped_column(Numeric(10,3))
    viscosity_snapshot:Mapped[Decimal]=mapped_column(Numeric(10,3))
    sulfur_snapshot:Mapped[Decimal]=mapped_column(Numeric(7,4))
