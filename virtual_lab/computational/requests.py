"""Validated inputs; credentials are deliberately absent from experiment records."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LENGTHS = (16384, 131072, 524288, 1048576)
OUTPUTS = (
    "ATAC", "CAGE", "DNASE", "RNA_SEQ", "CHIP_HISTONE", "CHIP_TF",
    "SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS", "CONTACT_MAPS", "PROCAP",
)


class InstrumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    hypothesis: str = Field(default="", max_length=4000)
    experiment_id: str = Field(default="", max_length=200)


class GenomeRequest(InstrumentRequest):
    instrument: Literal["alphagenome"] = "alphagenome"
    operation: Literal["interval", "sequence", "variant", "score", "ism"] = "variant"
    # This adapter deliberately uses the human hg38 model only.
    assembly: Literal["hg38"] = "hg38"
    chromosome: str = Field(default="chr1", pattern=r"^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)$")
    start: int = Field(default=0, ge=0)
    length: Literal[16384, 131072, 524288, 1048576] = 16384
    position: int | None = Field(default=None, ge=1)
    reference_bases: str = Field(default="", pattern=r"^[ACGT]*$", max_length=10000)
    alternate_bases: str = Field(default="", pattern=r"^[ACGT]*$", max_length=10000)
    sequence: str = Field(default="", pattern=r"^[ACGTN]*$", max_length=1048576)
    outputs: tuple[str, ...] = ("RNA_SEQ",)
    ontology_terms: tuple[str, ...] = ()
    ism_start: int | None = Field(default=None, ge=0)
    ism_width: int = Field(default=1, ge=1, le=32)
    model_version: Literal["ALL_FOLDS", "FOLD_0", "FOLD_1", "FOLD_2", "FOLD_3", "FOLD_4"] = "ALL_FOLDS"

    @model_validator(mode="after")
    def validate_protocol(self):
        import re
        if not self.outputs or len(set(self.outputs)) != len(self.outputs) or any(o not in OUTPUTS for o in self.outputs):
            raise ValueError("Choose one or more distinct supported output types.")
        if any(not re.fullmatch(r"(?:UBERON|CL|EFO):\d+", term) for term in self.ontology_terms):
            raise ValueError("Use ontology identifiers such as UBERON:0002048 or CL:0000540.")
        if self.operation == "sequence" and len(self.sequence) != self.length:
            raise ValueError("Sequence length must match the selected model window.")
        if self.operation != "sequence" and self.sequence:
            raise ValueError("A DNA sequence is only accepted for sequence prediction.")
        if self.operation in ("variant", "score"):
            if self.position is None or not self.reference_bases or not self.alternate_bases:
                raise ValueError("Variant position and both alleles are required (VCF-style, 1-based).")
            if self.reference_bases == self.alternate_bases:
                raise ValueError("Reference and alternate alleles must differ.")
            if not self.start <= self.position - 1 < self.position - 1 + len(self.reference_bases) <= self.start + self.length:
                raise ValueError("The complete reference allele must lie inside the 0-based prediction interval.")
        if self.operation == "ism":
            if self.ism_start is None or not self.start <= self.ism_start < self.ism_start + self.ism_width <= self.start + self.length:
                raise ValueError("The ISM region must lie inside the prediction interval.")
        if self.operation in ("score", "ism") and self.ontology_terms:
            raise ValueError("Scoring returns all model tracks; ontology filtering applies to predictions only.")
        return self


class StructureRequest(InstrumentRequest):
    instrument: Literal["alphafold_db"] = "alphafold_db"
    accession: str = Field(pattern=r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[1-9][0-9]*)?$")
    include_structure: bool = False
    include_pae: bool = False


def parse_request(data: dict) -> GenomeRequest | StructureRequest:
    if data.get("instrument") == "alphagenome":
        return GenomeRequest.model_validate(data)
    if data.get("instrument") == "alphafold_db":
        return StructureRequest.model_validate(data)
    raise ValueError("Unknown computational instrument.")
