from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|completed|failed
    error: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JsonType)
    n_ticks: Mapped[int] = mapped_column(default=0)


class TickMetric(Base):
    __tablename__ = "tick_metrics"
    __table_args__ = (Index("ix_tick_metrics_run_t", "run_id", "t"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"))
    t: Mapped[float]
    flows_total: Mapped[int]
    flows_reachable: Mapped[int]
    demand_gbps: Mapped[float | None]
    delivered_gbps: Mapped[float | None]
    delivery_ratio: Mapped[float | None]
    mean_latency_ms: Mapped[float | None]
    max_latency_ms: Mapped[float | None]
    loaded_links: Mapped[int]
    max_link_util: Mapped[float | None]
    congested_links: Mapped[int]
    overloaded_links: Mapped[int]
    handoffs: Mapped[int]
    outages: Mapped[int]
    links_added: Mapped[int]
    links_removed: Mapped[int]
    route_changes: Mapped[int] = mapped_column(server_default="0")
    mean_hops: Mapped[float | None]


class HandoffRecord(Base):
    __tablename__ = "handoff_events"
    __table_args__ = (Index("ix_handoff_events_run_t", "run_id", "t"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"))
    t: Mapped[float]
    station: Mapped[int]
    from_sat: Mapped[int | None]
    to_sat: Mapped[int | None]
    reason: Mapped[str] = mapped_column(String(20))


class FlowSample(Base):
    __tablename__ = "flow_samples"
    __table_args__ = (Index("ix_flow_samples_run_t", "run_id", "t"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"))
    t: Mapped[float]
    src: Mapped[str] = mapped_column(String(16))
    dst: Mapped[str] = mapped_column(String(16))
    demand_gbps: Mapped[float]
    reachable: Mapped[bool]
    latency_ms: Mapped[float | None]
    loss: Mapped[float | None]
    delivered_gbps: Mapped[float]
    hops: Mapped[int | None]
    max_util: Mapped[float | None]
    distinct_paths: Mapped[int]
    path: Mapped[list] = mapped_column(JsonType)


class LinkSample(Base):
    __tablename__ = "link_samples"
    __table_args__ = (Index("ix_link_samples_run_t", "run_id", "t"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"))
    t: Mapped[float]
    u: Mapped[str] = mapped_column(String(16))
    v: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    distance_km: Mapped[float]
    load_gbps: Mapped[float]
    capacity_gbps: Mapped[float]
    utilization: Mapped[float]
    queue_ms: Mapped[float]
    loss_eff: Mapped[float]

class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (UniqueConstraint("name", name="uq_scenarios_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())