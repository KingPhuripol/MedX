"""Node Library: Table 3.1 declarations and allowed providers."""

import pytest

from casegraph.library import LIBRARY, LibraryConfig, ProviderConfig, node_decls, output_types
from casegraph.types import NodeType as N

TABLE_3_1 = {
    # i2: the ClinicalText family (transcripts, extracted facts) and the voice_extract provider
    N.READER_TEXT: ({"ClinicalText", "IntakeTranscript", "VoiceIntakeFacts"}, {"Findings"},
                    {"voice_extract", "project_model", "external_model"}, False),
    N.READER_VITALS_LABS: ({"Vitals", "LabSeries"}, {"Findings"}, {"rules", "project_model"}, False),
    N.READER_CXR: ({"CXRImage"}, {"ImageTokens", "Findings"}, {"encoder_2d", "external_model", "classifier"}, False),
    N.READER_CT_MRI: ({"CTVolume", "MRIVolume"}, {"ImageTokens", "Findings"},
                      {"encoder_3d", "external_model", "segmentation"}, False),
    N.RED_FLAG: ({"Findings", "Vitals", "Demographics"}, {"Alerts"}, {"rules"}, True),  # i2: S4 reads age/sex
    N.PHARMA_AGENT: ({"MedicationList", "Findings"}, {"MedicationIssues"}, {"project_model", "rules"}, False),
    # i2: Reasoning builds the S4 Case for department.suggest from Demographics/Vitals directly
    N.REASONING: ({"Findings", "ImageTokens", "Alerts", "Demographics", "Vitals"},
                  {"CaseSummary", "DepartmentSuggestion", "CareSuggestion"},
                  {"project_model", "external_model"}, False),
    N.HUMAN_CHECKPOINT: ({"Alerts", "MedicationIssues", "CaseSummary", "DepartmentSuggestion", "CareSuggestion"},
                         {"ConfirmedResult"}, {"human:nurse", "human:physician", "human:pharmacist"}, True),
}


@pytest.mark.parametrize("node_type", list(N), ids=lambda t: t.value)
def test_table_3_1_declarations(node_type):
    decl = LIBRARY[node_type]
    inputs, outputs, providers, mandatory = TABLE_3_1[node_type]
    assert set(decl.input_types) == inputs
    assert set(decl.output_types) == outputs
    assert set(decl.allowed_providers) == providers
    assert decl.mandatory is mandatory
    assert isinstance(decl.required_inputs, tuple)


def test_imagetokens_only_from_encoders():
    assert output_types(N.READER_CXR, "encoder_2d") == ("ImageTokens",)
    assert output_types(N.READER_CT_MRI, "encoder_3d") == ("ImageTokens",)
    for t, p in [(N.READER_CXR, "external_model"), (N.READER_CXR, "classifier"),
                 (N.READER_CT_MRI, "external_model"), (N.READER_CT_MRI, "segmentation")]:
        assert output_types(t, p) == ("Findings",)


def test_reasoning_required_inputs_is_config_with_placeholder_default():
    assert LIBRARY[N.REASONING].required_inputs == ("Findings<-ClinicalText", "Findings<-Vitals")
    custom = node_decls(LibraryConfig(reasoning_required_inputs=("Findings<-ClinicalText",)))
    assert custom[N.REASONING].required_inputs == ("Findings<-ClinicalText",)
    assert "PLACEHOLDER" in LibraryConfig.__doc__


def test_default_provider_config_is_allowed():
    cfg = ProviderConfig()
    assert set(cfg.assignments) == set(N)
    for t, a in cfg.assignments.items():
        assert a.provider in LIBRARY[t].allowed_providers
