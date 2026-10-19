"""Human-authored plans and interpretations, separate from scientific results."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class ResultReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    observation_id: Identifier
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ResearchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    format: Literal["virtuallab-research-record"] = "virtuallab-research-record"
    schema_version: Literal[1] = 1
    id: Identifier
    experiment_id: Identifier
    record_type: Literal["plan", "conclusion"]
    research_question: Text
    created_at: str
    authored_by: Literal["researcher"] = "researcher"
    epistemic_state: Literal["MODEL_ASSUMPTION", "INFERRED"]
    content: dict[str, Text]
    plan_ref: ResultReference | None = None
    result_refs: Annotated[list[ResultReference], Field(max_length=100)] = Field(default_factory=list)
    planning_scope: Literal["not_evaluated", "before_selected_results", "retrospective"] = "not_evaluated"

    @model_validator(mode="after")
    def validate_record(self):
        timestamp = datetime.fromisoformat(self.created_at)
        if timestamp.tzinfo is None:
            raise ValueError("Research records require a timezone-aware timestamp.")
        if self.record_type == "plan":
            required = {"hypothesis", "method", "expected_outcome", "acceptance_criteria"}
            if self.epistemic_state != "MODEL_ASSUMPTION" or self.plan_ref or self.result_refs or self.planning_scope != "not_evaluated":
                raise ValueError("A research plan records assumptions, not results or a conclusion.")
        else:
            required = {"interpretation", "limitations", "decision"}
            if self.epistemic_state != "INFERRED" or self.plan_ref is None or not self.result_refs or self.planning_scope == "not_evaluated":
                raise ValueError("A conclusion needs a saved plan and explicitly selected results.")
            if self.content.get("decision") not in {"supports_within_scope", "does_not_support", "inconclusive"}:
                raise ValueError("Choose an explicit, scoped research decision.")
        if set(self.content) != required:
            raise ValueError("Research record fields do not match its type.")
        if len({r.observation_id for r in self.result_refs}) != len(self.result_refs):
            raise ValueError("Repeated evidence references are not allowed.")
        return self
