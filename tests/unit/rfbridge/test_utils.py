"""Unit tests for src/rfbridge/utils.py."""

import pytest

from src.rfbridge.utils import sanitise_topic_name


class TestSanitiseTopicName:
    def test_clean_name_unchanged(self):
        assert sanitise_topic_name("living_room") == "living_room"

    def test_space_replaced_by_underscore(self):
        assert sanitise_topic_name("EG Wohnkueche") == "EG_Wohnkueche"

    def test_umlaut_ue(self):
        assert sanitise_topic_name("Wohnküche") == "Wohnkueche"

    def test_umlaut_ae(self):
        assert sanitise_topic_name("Schlafzimmer Käthe") == "Schlafzimmer_Kaethe"

    def test_umlaut_oe(self):
        assert sanitise_topic_name("Flur Öst") == "Flur_Oest"

    def test_umlaut_ue_uppercase(self):
        assert sanitise_topic_name("Übergabe") == "Uebergabe"

    def test_umlaut_ae_uppercase(self):
        assert sanitise_topic_name("Äpfel") == "Aepfel"

    def test_umlaut_oe_uppercase(self):
        assert sanitise_topic_name("Öfen") == "Oefen"

    def test_eszett(self):
        assert sanitise_topic_name("Straße") == "Strasse"

    def test_full_example_eg_wohnkueche(self):
        assert sanitise_topic_name("EG Wohnküche") == "EG_Wohnkueche"

    def test_full_example_eg_arbeitszimmer(self):
        assert sanitise_topic_name("EG Arbeitszimmer") == "EG_Arbeitszimmer"

    def test_multiple_spaces_collapse(self):
        assert sanitise_topic_name("EG  Zimmer") == "EG_Zimmer"

    def test_hyphen_preserved(self):
        assert sanitise_topic_name("living-room") == "living-room"

    def test_special_chars_replaced(self):
        result = sanitise_topic_name("sensor/1")
        assert "/" not in result
        assert result == "sensor_1"

    def test_leading_trailing_underscores_stripped(self):
        assert sanitise_topic_name(" sensor ") == "sensor"
