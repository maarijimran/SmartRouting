from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    kind: Literal["local", "cloud"]
    provider: str = Field(min_length=1, max_length=64)
    endpoint: str
    provider_model: str | None = None
    context_limit: int = Field(gt=0)
    max_output: int = Field(gt=0)
    tokenizer: str = "fallback"
    quant: str | None = None
    min_ram_gb: float = Field(default=0, ge=0)
    min_vram_gb: float = Field(default=0, ge=0)
    enabled: bool = True


class ModelPriceCreate(BaseModel):
    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)
    source: str = Field(min_length=1, max_length=200)


class ModelResponse(ModelCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str


class ModelPriceResponse(ModelPriceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_id: str
    captured_at: datetime


class ModelPreferenceRequest(BaseModel):
    model_id: str
    connection_id: str | None = None
    enabled: bool = True
    tier: Literal["cheap", "strong"]


class ModelHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_id: str
    ts: datetime
    ok: bool
    p50_ms: float | None
    err_rate: float


class ModelPatch(BaseModel):
    enabled: bool | None = None
    context_limit: int | None = Field(default=None, gt=0)
    max_output: int | None = Field(default=None, gt=0)
    provider_model: str | None = None
    endpoint: str | None = None
