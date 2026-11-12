"""Representative multi-domain boards end to end: classification -> overlays -> composed rules -> compiled profile."""
import time
import unittest

from desk.domain_intelligence import api, get_library

CASES = [
    # (name, source, expected primary, must-have overlays, must-have rule ids, expected status)
    ("rf_board", {"text": "LoRaWAN EU868 sensor node, SX1262, battery powered 3.7 V li-ion, sleeps for years", "rf_region": "EU868", "rf_frequency_hz": 868e6,
                  "voltage_rails": {"VBAT": 4.2, "3V3": 3.3}, "current_limits_A": {"VBAT": 0.5, "3V3": 0.5}, "cells": 1, "chemistry": "li_ion",
                  "component_families_present": ["mcu", "rf_transceiver", "battery_protection_ic", "ntc_thermistor", "antenna"]},
     "lora_transceiver", ["rf_communication", "low_power", "battery_management"], ["LORA-BAND-110", "PLACE-ANT-014", "ROUTE-RF-022", "BAT-CHEM-130"], "READY"),
    ("high_current_power", {"text": "48 V to 12 V buck converter at 20 A for a server rack", "voltage_rails": {"VIN": 48.0, "12V": 12.0}, "current_limits_A": {"VIN": 6.0, "12V": 20.0},
                            "output_current_a": 20.0, "inductor_isat_a": 30.0, "ic_vin_min": 9.0, "ic_vin_max": 60.0},
     "buck_converter", ["switching_power", "high_current", "thermal_management"], ["ELEC-WIDTH-001", "PWR-ROUTE-170", "DCDC-ISAT-120", "ELEC-VIA-005"], "READY"),
    ("ac_mains", {"text": "230 V AC mains input section with fuse, MOV, X capacitor and bridge rectifier, non-isolated", "mains": True, "isolation": False,
                  "voltage_rails": {"MAINS_L": 230.0, "MAINS_N": 230.0, "VBULK": 325.0}, "current_limits_A": {"MAINS_L": 1.0, "MAINS_N": 1.0, "VBULK": 0.5},
                  "component_families_present": ["fuse", "mov_varistor", "x_capacitor", "discharge_resistor", "bridge_rectifier", "bulk_capacitor"]},
     "ac_mains_input_protection", ["mains_safety_isolation", "emi_emc"], ["ELEC-CREEP-004", "MAINS-DECL-160", "MAINS-FUSE-161", "MAINS-XDIS-162", "COPPER-BARRIER-044"], "READY"),
    ("dcdc_isolated", {"text": "isolated flyback converter 24 V DC to 5 V 2 A, 1.5 kV isolation, reinforced", "isolation": True, "isolation_voltage_v": 1500.0, "insulation_grade": "reinforced",
                       "voltage_rails": {"VIN": 24.0, "5V": 5.0}, "current_limits_A": {"VIN": 0.6, "5V": 2.0}, "ic_vin_min": 9.0, "ic_vin_max": 60.0},
     "flyback_converter", ["switching_power", "galvanic_isolation"], ["ELEC-CREEP-004", "PLACE-ISO-016", "ROUTE-HV-025", "MAINS-INS-163"], "READY"),
    ("motor", {"text": "24 V 3-phase BLDC motor controller, 10 A peak, 6 A continuous, ESP32 and CAN", "peak_current_a": 10.0, "continuous_current_a": 6.0, "fet_id_rating_a": 30.0,
               "voltage_rails": {"VBUS": 24.0, "3V3": 3.3}, "current_limits_A": {"VBUS": 10.0, "3V3": 0.6}},
     "three_phase_bldc_controller", ["motor_drive", "high_current", "can_interface"], ["MOTOR-PEAK-140", "ROUTE-POLY-026", "PLACE-SENSE-018", "ROUTE-DIFF-021"], "READY"),
    ("battery", {"text": "13S li-ion BMS for an e-bike, 30 A discharge, CAN", "cells": 13, "chemistry": "li_ion", "voltage_rails": {"PACK+": 54.6}, "current_limits_A": {"PACK+": 30.0},
                 "component_families_present": ["battery_monitor_afe", "mosfet", "current_sense_resistor", "ntc_thermistor", "fuse", "can_transceiver"]},
     "battery_management_system", ["battery_management", "high_current", "can_interface"], ["BAT-CHEM-130", "BAT-PROT-131", "BAT-NTC-132", "PWR-ROUTE-170"], "READY"),
    ("embedded", {"text": "ESP32-S3 IoT controller with USB-C, Wi-Fi, 5 V USB input", "voltage_rails": {"VBUS": 5.0, "3V3": 3.3}, "current_limits_A": {"VBUS": 1.0, "3V3": 0.8},
                  "regulator_rating_a": 1.0, "usb_role": "sink", "cc_resistors": {"CC1": 5100, "CC2": 5100, "type": "pulldown"}},
     "esp32_dev_board", ["rf_communication", "usb_interface"], ["MCU-RADIO-101", "USBC-CC-150", "MCU-USB-102", "PLACE-ANT-014"], "READY"),
    ("high_speed", {"text": "Artix-7 FPGA board with DDR3 memory and a PCIe x4 edge connector", "voltage_rails": {"12V": 12.0, "1V0": 1.0}, "current_limits_A": {"12V": 3.0, "1V0": 6.0}},
     "fpga_dev_board", ["high_speed_digital", "thermal_management"], ["ROUTE-DIFF-021", "ROUTE-RETURN-027", "COPPER-GND-040"], "READY"),
    ("analog", {"text": "24-bit delta-sigma strain gauge load cell amplifier with 2.5 V reference", "voltage_rails": {"5V": 5.0}, "current_limits_A": {"5V": 0.1}},
     "strain_gauge_loadcell_amplifier", ["precision_analog"], ["ROUTE-GUARD-030", "PLACE-THERM-017", "ELEC-CLEAR-003"], "READY"),
]


class CrossDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()

    def test_cases(self):
        failures = []
        for name, src, primary, overlays, rule_ids, status in CASES:
            out = api.validate_requirements(src, project_id=name, lib=self.lib)
            c, cp = out["classification"], out["compiled"]
            if c["primary_archetype"] != primary:
                failures.append(f"{name}: primary {c['primary_archetype']} != {primary}; top {[(x['archetype_id'], x['score']) for x in c['candidates'][:3]]}")
            for ov in overlays:
                if ov not in c["required_overlays"]:
                    failures.append(f"{name}: overlay {ov} missing from {c['required_overlays']}")
            for rid in rule_ids:
                if rid not in cp["rule_ids"]:
                    failures.append(f"{name}: rule {rid} not composed")
            if cp["status"] != status:
                failures.append(f"{name}: status {cp['status']} != {status}; blocking {cp['blocking_issues']}; conflicts {c['conflicts']}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_overlays_change_the_rule_set(self):
        plain = api.rules_for("buck_converter", overlays=["switching_power"], lib=self.lib)
        hv = api.rules_for("buck_converter", overlays=["switching_power", "high_current", "mains_safety_isolation"], lib=self.lib)
        self.assertGreater(len(hv["rules"]), len(plain["rules"]))
        self.assertIn("ELEC-CREEP-004", [r["rule_id"] for r in hv["rules"]])
        self.assertNotIn("ELEC-CREEP-004", [r["rule_id"] for r in plain["rules"]])

    def test_agent_context_is_compact_and_honest(self):
        ctx = api.agent_context("three_phase_bldc_controller", lib=self.lib, budget_chars=3000)
        self.assertLessEqual(len(ctx), 3000)
        self.assertIn("ENFORCED RULES", ctx)
        self.assertIn("ADVISORY / UNSUPPORTED", ctx)
        self.assertIn("never guess", ctx)

    def test_end_to_end_latency_and_token_size(self):
        t0 = time.perf_counter()
        for _ in range(5):
            api.validate_requirements(CASES[4][1], project_id="bench", lib=self.lib)
        per = (time.perf_counter() - t0) / 5
        self.assertLess(per, 0.5, f"{per*1000:.0f} ms per validate")
        ctx = api.agent_context("esp32_dev_board", lib=self.lib)
        self.assertLess(len(ctx) / 4, 900, "agent context should stay under ~900 tokens")


if __name__ == "__main__":
    unittest.main()
