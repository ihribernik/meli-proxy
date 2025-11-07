from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class RateLimitIPPathRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip: str = Field(min_length=1)
    path_prefix: str = Field(min_length=1)
    limit: PositiveInt


class RateLimitRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip: Dict[str, PositiveInt] = Field(default_factory=dict)
    path: Dict[str, PositiveInt] = Field(default_factory=dict)
    ip_path: List[RateLimitIPPathRule] = Field(default_factory=list)
    updated_at: Optional[float] = None


class RateLimitRulesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip: Optional[Dict[str, PositiveInt]] = None
    path: Optional[Dict[str, PositiveInt]] = None
    ip_path: Optional[List[RateLimitIPPathRule]] = None
