"""Deterministic requirement extraction and classification, including ambiguity and safety behaviour."""
import time
import unittest

from desk.domain_intelligence import api, get_library
from desk.domain_intelligence.classifier import extract_requirements, classify

CASES = {
    "esp32_dev_board": "ESP32-S3 development board with USB-C programming, Wi-Fi and BLE, powered from 5 V USB",
    "stm32_controller": "STM32F4 controller board, 12 V input, CAN bus, SWD debug, 3.3 V logic",
    "lora_transceiver": "LoRaWAN end node, SX1262 transceiver, EU868 at 868 MHz, battery powered 3.7 V li-ion",
    "buck_converter": "12 V to 3.3 V buck step-down converter, 3 A output, 500 kHz switching",
    "boost_converter": "boost converter from a single li-ion 3.7 V to 12 V at 1 A",
    "single_cell_liion_charger": "single cell li-ion charger from USB 5 V, 1 A charge current, NTC",
    "battery_management_system": "13S li-ion battery management system BMS for an e-bike, 30 A discharge, CAN",
    "three_phase_bldc_controller": "24 V input motor controller with a 3-phase BLDC motor, 10 A peak current, ESP32 control and CAN communication",
    "usb_c_interface": "USB-C interface board with CC logic, 5 V 3 A sink, ESD protection",
    "ac_mains_input_protection": "230 V AC mains input section with fuse, MOV, EMI filter and bridge rectifier",
    "isolated_ac_dc": "offline isolated AC-DC adapter 230 V to 12 V 2 A SELV flyback",
    "wearable_electronics": "smartwatch wearable with BLE, li-po, PPG heart rate, 1.3 inch display",
    "obd_can_telematics": "OBD-II telematics dongle with CAN, LTE modem and GPS for fleet tracking",
    "precision_adc_frontend": "24-bit delta-sigma data acquisition front end with 2.5 V reference, 8 channels",
    "fpga_dev_board": "Artix-7 FPGA development board with DDR3 and PCIe x4",
    "stepper_driver": "TMC2209 stepper motor driver for a 3D printer, 24 V, 2 A per phase",
    "class_d_amplifier": "class-D audio amplifier 2x20 W into 4 ohm speakers from 12 V",
    "gigabit_ethernet_board": "gigabit ethernet RGMII PHY board with RJ45 magnetics",
}


class ExtractionTests(unittest.TestCase):
    def test_numbers_units_and_protocols(self):
        r = extract_requirements("24 V input, 10 A peak current, 2.4 GHz Wi-Fi and CAN bus, 500 kHz switching, -40 to 85 °C outdoor")
        f = r.features
        self.assertEqual(f["input_voltage_v"], 24.0)
        self.assertEqual(f["current_a"], 10.0)
        self.assertEqual(f["peak_current_a"], 10.0)
        self.assertEqual(f["rf_frequency_hz"], 2.4e9)
        self.assertEqual(f["switching_frequency_hz"], 500e3)
        self.assertEqual(f["protocols"], ["can", "wifi"])
        self.assertEqual(f["max_ambient_c"], 85.0)
        self.assertEqual(f["environment"], "outdoor")

    def test_a_voltage_beside_a_current_is_never_read_as_a_current(self):
        # Regression: the range separator ".." was an unescaped regex, so "24 V, 2 A" parsed as a 24..2 A range.
        cases = {"24 V, 2 A": (2.0, [24.0]), "5 V 3 A buck": (3.0, [5.0]), "5V/3A USB-C PD sink": (3.0, [5.0]),
                 "12 V 1.5 A input, 5 V 3 A output": (3.0, [5.0, 12.0]),
                 "12 V input, 5 V 3 A synchronous buck converter module, 500 kHz switching": (3.0, [5.0, 12.0])}
        for text, (amps, volts) in cases.items():
            f = extract_requirements(text).features
            self.assertEqual(f["current_a"], amps, text)
            self.assertEqual(f["voltages_v"], volts, text)

    def test_ranges_with_one_unit_still_parse(self):
        for text, key, want in (("4.5-5.5 V input", "voltages_v", [4.5, 5.5]), ("9–36 V input", "voltages_v", [9.0, 36.0]),
                                ("2 to 3 A load", "current_a", 3.0), ("3..5 A load", "current_a", 5.0),
                                ("100 mA to 2 A load", "current_a", 2.0)):
            self.assertEqual(extract_requirements(text).features[key], want, text)

    def test_structured_fields_override_text(self):
        r = extract_requirements({"text": "12 V board", "input_voltage_v": 48.0, "protocols": ["rs485"], "voltage_rails": {"VIN": 48.0}})
        self.assertEqual(r.features["input_voltage_v"], 48.0)
        self.assertEqual(r.features["protocols"], ["rs485"])
        self.assertEqual(r.features["voltage_rails"], {"VIN": 48.0})
        self.assertIn("voltage_rails", r.provided_fields)

    def test_mains_and_isolation_detection(self):
        self.assertTrue(extract_requirements("230 V AC mains powered timer").features.get("mains"))
        self.assertTrue(extract_requirements("isolated RS-485 with 2.5 kV barrier").features.get("isolation"))
        self.assertIs(extract_requirements("transformerless capacitive dropper night light").features.get("isolation"), False)
        self.assertEqual(extract_requirements("4S LiFePO4 pack").features.get("cells"), 4)
        self.assertEqual(extract_requirements("4S LiFePO4 pack").features.get("chemistry"), "lifepo4")


class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()

    def test_representative_sentences_classify_to_the_expected_archetype(self):
        misses = []
        for want, text in CASES.items():
            r = classify(text, self.lib)
            if r.primary_archetype != want:
                misses.append(f"{want} -> {r.primary_archetype} ({[(c.archetype_id, c.score) for c in r.candidates[:3]]})")
        self.assertEqual(misses, [], "\n".join(misses))

    def test_classification_is_deterministic_and_explains_itself(self):
        a = classify(CASES["buck_converter"], self.lib)
        b = classify(CASES["buck_converter"], self.lib)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertTrue(a.evidence)
        self.assertTrue(any("keyword" in e for e in a.evidence))
        self.assertGreater(a.confidence, 0.6)
        self.assertEqual(a.classification_status, "CLASSIFIED")

    def test_motor_controller_example_from_directive(self):
        r = classify("I need a 24 V input motor controller with a 3-phase BLDC motor, 10 A peak current, ESP32 control and CAN communication.", self.lib)
        self.assertEqual(r.primary_archetype, "three_phase_bldc_controller")
        for ov in ("motor_drive", "high_current", "thermal_management", "emi_emc", "can_interface"):
            self.assertIn(ov, r.required_overlays)
        for fam in ("mcu", "three_phase_gate_driver", "mosfet", "current_sense_resistor", "dc_link_capacitor", "can_transceiver"):
            self.assertIn(fam, r.required_component_families)
        self.assertTrue(r.missing_information)

    def test_ambiguous_wording_requires_review_or_is_unclassified(self):
        r = classify("a small board for my project with some connectors", self.lib)
        self.assertIn(r.classification_status, ("REVIEW_REQUIRED", "UNCLASSIFIED"))
        self.assertLess(r.confidence, 0.7)
        self.assertTrue(r.missing_information)

    def test_mains_is_never_silently_dropped(self):
        # a sensor node that happens to be mains powered: primary is embedded, but mains safety stays on and review is required
        r = classify("ESP32 temperature sensor node powered directly from 230 V AC mains", self.lib)
        self.assertIn("mains_safety_isolation", r.required_overlays)
        self.assertEqual(r.classification_status, "REVIEW_REQUIRED")
        self.assertTrue(any("mains" in c for c in r.conflicts))
        self.assertTrue(any("voltage_rails" in m for m in r.missing_information))
        self.assertIn(r.primary_archetype, ("ac_mains_input_protection", "low_power_sensor_node", "esp32_dev_board", "non_isolated_ac_dc"))

    def test_interface_feature_does_not_hide_the_controller(self):
        r = classify(CASES["stm32_controller"], self.lib)
        self.assertEqual(r.primary_archetype, "stm32_controller")
        self.assertIn("can_bus_interface", r.secondary_archetypes)

    def test_overlays_follow_features_not_only_the_archetype(self):
        r = classify("buck converter 48 V to 12 V at 20 A with conformal coating for outdoor use", self.lib)
        self.assertIn("high_current", r.required_overlays)
        self.assertIn("harsh_environment", r.required_overlays)

    def test_classification_latency(self):
        t0 = time.perf_counter()
        for _ in range(10):
            classify(CASES["three_phase_bldc_controller"], self.lib)
        per = (time.perf_counter() - t0) / 10
        self.assertLess(per, 0.25, f"{per*1000:.0f} ms per classification")

    def test_api_shortcuts(self):
        self.assertTrue(api.search("lora long range")[0]["archetype_id"] == "lora_transceiver")
        d = api.show("buck_converter")
        self.assertIn("rules", d)
        self.assertTrue(any(r["rule_id"] == "DCDC-ISAT-120" for r in d["rules"]))


if __name__ == "__main__":
    unittest.main()
