# Taxonomy reference: 14 domains, 100 PCB archetypes

Generated from `library/pcb_domains/` (version 1.0.0@2026-11-12). Edit the JSON, not this file; regenerate with the scratch generator or by hand.

Maturity: DRAFT = knowledge entry only; OFFLINE_TESTED = its rule set is exercised by `tests/test_cross_domain_cases.py` or the rule-engine tests. No entry claims VERIFIED_AGAINST_SOURCE: standards tables in `desk/ipc.py` are transcriptions awaiting a human check.

## Embedded systems and MCU boards (`embedded_mcu`, 10)

Microcontroller-centred boards: a low-voltage digital core with regulated rails, peripherals, sensors and communication interfaces.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `esp32_dev_board` | ESP32 development board | OFFLINE_TESTED | rf_communication, usb_interface, low_power | 26 | mcu_wireless_module, ldo_regulator, usb_connector, esd_protection, decoupling_capacitor |
| `stm32_controller` | STM32 controller board | OFFLINE_TESTED | low_power, industrial_interfaces | 19 | mcu, ldo_regulator, crystal, decoupling_capacitor, debug_header |
| `rp2040_dev_board` | RP2040 development board | DRAFT | usb_interface | 19 | mcu, qspi_flash, ldo_regulator, crystal, usb_connector, decoupling_capacitor |
| `low_power_sensor_node` | Low-power sensor node | DRAFT | low_power, rf_communication, battery_management | 24 | mcu, load_switch, environmental_sensor, decoupling_capacitor |
| `industrial_remote_io` | Industrial remote I/O controller | DRAFT | industrial_interfaces, galvanic_isolation, harsh_environment | 22 | mcu, buck_regulator, digital_isolator, tvs_diode, terminal_block |
| `embedded_data_logger` | Embedded data logger | DRAFT | low_power, usb_interface | 18 | mcu, sd_card_socket, rtc, crystal, ldo_regulator, decoupling_capacitor |
| `wearable_electronics` | Wearable electronics | OFFLINE_TESTED | rf_communication, battery_management, low_power, precision_analog | 29 | mcu_wireless_module, li_ion_charger, battery_protection_ic, ldo_regulator, antenna, decoupling_capacitor |
| `mcu_carrier_board` | MCU/SoM carrier board | DRAFT | high_speed_digital, usb_interface | 18 | board_to_board_connector, buck_regulator, decoupling_capacitor |
| `battery_iot_node` | Battery-powered IoT node | DRAFT | rf_communication, battery_management, low_power, harsh_environment | 26 | mcu, rf_transceiver, buck_regulator, antenna, decoupling_capacitor |
| `multi_sensor_controller` | Multi-sensor controller | DRAFT | precision_analog | 17 | mcu, ldo_regulator, environmental_sensor, decoupling_capacitor |

## RF and wireless communication (`rf_wireless`, 10)

Boards carrying radio-frequency signals: transceivers, front ends, antennas and matching networks where trace geometry is part of the circuit.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `wifi_ble_module_board` | Wi-Fi and Bluetooth board | DRAFT | rf_communication | 22 | mcu_wireless_module, antenna, ldo_regulator, decoupling_capacitor |
| `lora_transceiver` | LoRa transceiver board | OFFLINE_TESTED | rf_communication, low_power | 22 | rf_transceiver, rf_matching_component, antenna, mcu, decoupling_capacitor |
| `subghz_transmitter` | Sub-GHz RF transmitter/transceiver | DRAFT | rf_communication, low_power | 22 | rf_transceiver, rf_matching_component, antenna, decoupling_capacitor |
| `gnss_receiver` | GNSS receiver board | DRAFT | rf_communication, low_power | 20 | gnss_module, antenna, ldo_regulator, decoupling_capacitor |
| `cellular_lte_nbiot` | Cellular LTE/NB-IoT board | DRAFT | rf_communication, high_current, battery_management | 27 | cellular_module, sim_holder, antenna, buck_regulator, bulk_capacitor, decoupling_capacitor |
| `rf_front_end` | RF front-end board | DRAFT | rf_communication, thermal_management | 24 | power_amplifier, rf_switch, rf_matching_component, decoupling_capacitor |
| `antenna_matching_network` | Antenna matching network board | DRAFT | rf_communication | 20 | antenna, rf_matching_component |
| `sdr_hardware` | Software-defined radio hardware | DRAFT | rf_communication, high_speed_digital, precision_analog, thermal_management | 26 | rf_transceiver, fpga, clock_generator, buck_regulator, ldo_regulator, decoupling_capacitor |
| `uwb_communication` | UWB ranging/communication board | DRAFT | rf_communication, low_power | 21 | rf_transceiver, antenna, crystal, mcu, decoupling_capacitor |
| `rf_measurement_hardware` | RF measurement hardware | DRAFT | rf_communication, precision_analog | 22 | rf_detector, rf_connector, adc, decoupling_capacitor |

## DC-DC power electronics (`dcdc_power`, 10)

Switched-mode converters: a switching node, magnetics, rectification and control loop where loop area, copper and thermal design decide the result.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `buck_converter` | Buck (step-down) converter | OFFLINE_TESTED | switching_power, thermal_management, emi_emc | 30 | buck_regulator, inductor, input_capacitor, output_capacitor, feedback_resistor |
| `boost_converter` | Boost (step-up) converter | OFFLINE_TESTED | switching_power, thermal_management, emi_emc | 31 | boost_regulator, inductor, output_capacitor, input_capacitor, feedback_resistor |
| `buck_boost_converter` | Buck-boost converter | DRAFT | switching_power, thermal_management, emi_emc | 30 | buck_boost_regulator, inductor, input_capacitor, output_capacitor, feedback_resistor |
| `flyback_converter` | Flyback converter | DRAFT | switching_power, galvanic_isolation, thermal_management, emi_emc | 33 | flyback_controller, flyback_transformer, schottky_diode, output_capacitor, input_capacitor |
| `forward_converter` | Forward converter | DRAFT | switching_power, galvanic_isolation, thermal_management, emi_emc | 35 | pwm_controller, mosfet, power_transformer, output_inductor, schottky_diode, output_capacitor, input_capacitor |
| `push_pull_converter` | Push-pull converter | DRAFT | switching_power, galvanic_isolation, high_current, thermal_management, emi_emc | 37 | pwm_controller, mosfet, gate_driver, power_transformer, output_capacitor, input_capacitor |
| `half_bridge_converter` | Half-bridge converter | DRAFT | switching_power, galvanic_isolation, thermal_management, emi_emc, mains_safety_isolation | 38 | pwm_controller, mosfet, gate_driver, power_transformer, output_capacitor, input_capacitor |
| `full_bridge_converter` | Full-bridge converter | DRAFT | switching_power, galvanic_isolation, high_current, thermal_management, emi_emc, mains_safety_isolation | 40 | pwm_controller, gate_driver, power_transformer, dc_link_capacitor, output_capacitor |
| `dual_active_bridge` | Dual-active-bridge converter | DRAFT | switching_power, galvanic_isolation, high_current, thermal_management, emi_emc, mains_safety_isolation | 40 | mcu, gate_driver, power_transformer, dc_link_capacitor, current_transformer |
| `poe_power_board` | PoE powered-device power board | DRAFT | switching_power, galvanic_isolation, emi_emc | 31 | poe_pd_controller, ethernet_magnetics, rj45_connector, bridge_rectifier, flyback_transformer, output_capacitor |

## AC mains and high-voltage electronics (`ac_mains_hv`, 8)

Boards connected to mains or carrying hazardous voltages: creepage, clearance, isolation barriers and protective components are the design.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `ac_mains_input_protection` | AC mains input and protection | OFFLINE_TESTED | mains_safety_isolation, emi_emc | 27 | mains_connector, fuse, mov_varistor, x_capacitor, bridge_rectifier, bulk_capacitor |
| `isolated_ac_dc` | Isolated AC-DC converter | OFFLINE_TESTED | mains_safety_isolation, switching_power, galvanic_isolation, emi_emc, thermal_management | 38 | fuse, bridge_rectifier, bulk_capacitor, flyback_controller, flyback_transformer, optocoupler, output_capacitor |
| `non_isolated_ac_dc` | Non-isolated AC-DC (capacitive dropper / buck) | OFFLINE_TESTED | mains_safety_isolation, thermal_management | 30 | fuse, bridge_rectifier, bulk_capacitor, zener_diode |
| `triac_controller` | Triac/SCR mains controller | DRAFT | mains_safety_isolation, thermal_management, emi_emc | 29 | triac, opto_triac_driver, fuse, mains_connector |
| `ac_motor_controller` | AC motor controller / inverter | DRAFT | mains_safety_isolation, motor_drive, high_current, thermal_management, emi_emc, galvanic_isolation | 39 | bridge_rectifier, dc_link_capacitor, igbt, gate_driver, mcu, fuse |
| `mains_lighting_driver` | Mains LED lighting driver | DRAFT | mains_safety_isolation, switching_power, thermal_management, emi_emc | 41 | led_driver_offline, bridge_rectifier, bulk_capacitor, fuse, current_sense_resistor, output_capacitor |
| `pfc_board` | Power-factor-correction stage | DRAFT | mains_safety_isolation, switching_power, high_current, thermal_management, emi_emc | 42 | pfc_controller, mosfet, sic_diode, boost_inductor_pfc, bulk_capacitor, bridge_rectifier, current_sense_resistor |
| `hv_monitoring_board` | High-voltage monitoring board | DRAFT | mains_safety_isolation, galvanic_isolation, precision_analog | 28 | voltage_sense_divider, isolated_amplifier, digital_isolator, mcu |

## Batteries, charging and BMS (`battery_bms`, 8)

Boards that charge, protect, balance or monitor battery cells and manage the power path between source, battery and load.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `single_cell_liion_charger` | Single-cell Li-ion charger | OFFLINE_TESTED | battery_management, usb_interface, thermal_management | 25 | li_ion_charger, battery_connector, input_capacitor, output_capacitor |
| `multi_cell_charger` | Multi-cell battery charger | DRAFT | battery_management, switching_power, high_current, thermal_management | 35 | switching_charger, inductor, current_sense_resistor, battery_connector, input_capacitor, output_capacitor |
| `battery_management_system` | Battery management system | OFFLINE_TESTED | battery_management, high_current, thermal_management, can_interface | 30 | battery_monitor_afe, mosfet, current_sense_resistor, mcu, fuse, battery_connector |
| `cell_balancing_board` | Cell-balancing board | DRAFT | battery_management, thermal_management | 24 | balancing_resistor, mosfet, cell_tap_connector |
| `battery_protection_board` | Battery protection board | DRAFT | battery_management, high_current | 24 | battery_protection_ic, mosfet, battery_connector |
| `power_path_management` | Power-path management board | DRAFT | battery_management, usb_interface | 21 | pmic_power_path, load_switch, input_capacitor, output_capacitor |
| `solar_battery_controller` | Solar battery charge controller | DRAFT | battery_management, switching_power, harsh_environment, thermal_management | 34 | mppt_charge_controller, inductor, current_sense_resistor, battery_connector, input_capacitor, output_capacitor |
| `battery_fuel_gauge` | Battery fuel-gauge board | DRAFT | battery_management, precision_analog, low_power | 23 | fuel_gauge, current_sense_resistor, battery_connector |

## Motor control and motion electronics (`motor_control`, 8)

Drive stages and control electronics for motors and actuators: power switches, gate drives, current sensing, protection and feedback interfaces.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `three_phase_bldc_controller` | Three-phase BLDC/PMSM controller | OFFLINE_TESTED | motor_drive, high_current, thermal_management, emi_emc, can_interface | 31 | mcu, three_phase_gate_driver, mosfet, current_sense_resistor, dc_link_capacitor, motor_connector |
| `brushed_dc_h_bridge` | Brushed DC H-bridge driver | DRAFT | motor_drive, high_current, thermal_management | 29 | h_bridge_driver, bulk_capacitor, motor_connector |
| `stepper_driver` | Stepper motor driver | DRAFT | motor_drive, thermal_management | 29 | stepper_driver_ic, bulk_capacitor, motor_connector |
| `servo_controller` | Servo drive controller | DRAFT | motor_drive, high_current, thermal_management, emi_emc, industrial_interfaces | 32 | mcu, mosfet, current_sense_resistor, encoder_interface, dc_link_capacitor, motor_connector |
| `solenoid_relay_driver` | Solenoid and relay driver board | DRAFT | motor_drive, industrial_interfaces, thermal_management | 29 | low_side_switch, flyback_diode, terminal_block |
| `fan_pump_controller` | Fan and pump controller | DRAFT | motor_drive | 27 | mcu, low_side_switch, fan_connector |
| `encoder_feedback_interface` | Encoder and feedback interface | DRAFT | industrial_interfaces, precision_analog | 19 | rs422_receiver, esd_protection, terminal_block |
| `industrial_vfd_gate_drive` | Industrial gate-drive board (IGBT/SiC) | DRAFT | galvanic_isolation, mains_safety_isolation, motor_drive, emi_emc | 35 | isolated_gate_driver, isolated_dc_dc_module, gate_resistor, decoupling_capacitor |

## Analog, sensors and instrumentation (`analog_sensors`, 8)

Low-noise measurement chains: sensor, conditioning, ADC and reference, where grounding, guarding and noise coupling decide accuracy.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `precision_adc_frontend` | Precision ADC front end | DRAFT | precision_analog | 17 | adc, voltage_reference, ldo_regulator, precision_resistor |
| `thermocouple_rtd_measurement` | Thermocouple / RTD measurement | DRAFT | precision_analog, galvanic_isolation | 21 | thermocouple_converter, terminal_block, precision_resistor |
| `strain_gauge_loadcell_amplifier` | Strain gauge / load cell amplifier | DRAFT | precision_analog | 17 | bridge_adc, terminal_block, precision_resistor |
| `current_voltage_measurement` | Current and voltage measurement board | DRAFT | precision_analog, high_current | 23 | current_sense_resistor, current_sense_amplifier, voltage_sense_divider |
| `environmental_sensor_board` | Environmental sensor board | DRAFT | precision_analog, low_power | 17 | environmental_sensor, mcu, decoupling_capacitor |
| `imu_motion_sensor_board` | IMU / motion sensor board | DRAFT | precision_analog | 18 | imu, mcu, decoupling_capacitor |
| `photodiode_optical_frontend` | Photodiode / optical front end | DRAFT | precision_analog | 17 | photodiode, op_amp, precision_resistor |
| `ph_electrochemical_frontend` | pH / electrochemical sensor front end | DRAFT | precision_analog, galvanic_isolation | 21 | op_amp, bnc_connector, voltage_reference |

## High-speed digital and computing (`high_speed_digital`, 8)

Boards with controlled-impedance buses, memory and multi-gigabit interfaces where stackup, length matching and reference planes are mandatory.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `fpga_dev_board` | FPGA development board | DRAFT | high_speed_digital, thermal_management | 21 | fpga, configuration_flash, buck_regulator, clock_generator, decoupling_capacitor, debug_header |
| `mpu_som_carrier` | MPU/Linux SoM carrier | DRAFT | high_speed_digital, usb_interface, thermal_management | 22 | board_to_board_connector, buck_regulator, esd_protection, decoupling_capacitor |
| `ddr_memory_subsystem` | DDR memory subsystem | DRAFT | high_speed_digital | 17 | ddr_memory, ddr_termination_regulator, decoupling_capacitor |
| `pcie_add_in_card` | PCIe add-in card | DRAFT | high_speed_digital, thermal_management | 21 | pcie_endpoint, card_edge_connector, buck_regulator, decoupling_capacitor |
| `gigabit_ethernet_board` | Gigabit Ethernet interface | DRAFT | high_speed_digital, emi_emc, galvanic_isolation | 23 | ethernet_phy, ethernet_magnetics, rj45_connector, crystal, decoupling_capacitor |
| `mipi_camera_board` | MIPI camera board | DRAFT | high_speed_digital, precision_analog | 20 | image_sensor, mipi_connector, ldo_regulator, decoupling_capacitor |
| `high_speed_adc_dac_board` | High-speed ADC/DAC board | DRAFT | high_speed_digital, precision_analog | 19 | high_speed_adc, clock_generator, ldo_regulator, decoupling_capacitor |
| `nvme_storage_board` | NVMe / storage board | DRAFT | high_speed_digital, thermal_management | 21 | m2_connector, buck_regulator, decoupling_capacitor |

## Interfaces and communication electronics (`interfaces_comms`, 8)

Boards whose purpose is a wired interface: transceivers, protection and connectors that must meet an interface standard's electrical rules.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `usb_c_interface` | USB-C interface board | OFFLINE_TESTED | usb_interface, emi_emc | 20 | usb_c_connector, esd_protection, decoupling_capacitor |
| `usb_hub_board` | USB hub board | DRAFT | usb_interface | 18 | usb_hub_controller, usb_connector, load_switch, esd_protection, crystal |
| `can_bus_interface` | CAN bus interface | DRAFT | can_interface, emi_emc, industrial_interfaces | 18 | can_transceiver, tvs_diode, terminal_block |
| `rs485_modbus_interface` | RS-485 / Modbus interface | DRAFT | industrial_interfaces, galvanic_isolation, emi_emc | 22 | rs485_transceiver, tvs_diode, terminal_block |
| `fast_ethernet_interface` | 10/100 Ethernet interface | DRAFT | emi_emc, galvanic_isolation | 21 | ethernet_phy, ethernet_magnetics, rj45_connector, crystal, decoupling_capacitor |
| `isolated_serial_interface` | Isolated serial interface (UART/SPI/I2C) | DRAFT | galvanic_isolation | 19 | digital_isolator, isolated_dc_dc_module, decoupling_capacitor |
| `i2c_spi_expander_board` | I2C/SPI expander and level-shift board | DRAFT |  | 15 | gpio_expander, level_shifter, pin_header, decoupling_capacitor |
| `usb_pd_sink_board` | USB-PD sink/source power board | DRAFT | usb_interface, switching_power, high_current | 32 | usb_c_connector, usb_pd_controller, load_switch, tvs_diode |

## Audio and video electronics (`audio_video`, 5)

Audio amplification, conversion and capture, and digital video interfaces: noise, grounding and output filtering set the quality.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `class_d_amplifier` | Class-D audio amplifier | DRAFT | switching_power, thermal_management, emi_emc | 29 | class_d_amplifier_ic, output_inductor, bulk_capacitor, speaker_connector, decoupling_capacitor |
| `audio_codec_dac_board` | Audio codec / DAC board | DRAFT | precision_analog | 18 | audio_codec, crystal, ldo_regulator, audio_jack |
| `microphone_array_board` | Microphone array board | DRAFT | precision_analog | 17 | mems_microphone, ldo_regulator, decoupling_capacitor |
| `hdmi_interface_board` | HDMI interface board | DRAFT | high_speed_digital, emi_emc | 18 | hdmi_connector, esd_protection, decoupling_capacitor |
| `headphone_line_amplifier` | Headphone / line amplifier | DRAFT | precision_analog | 17 | op_amp, audio_jack, film_capacitor |

## Industrial automation and control (`industrial_control`, 5)

Controllers and I/O for industrial environments: isolated inputs and outputs, 24 V supplies, relays, fieldbuses and surge immunity.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `plc_io_module` | PLC I/O module | DRAFT | industrial_interfaces, galvanic_isolation, harsh_environment | 22 | digital_isolator, tvs_diode, terminal_block, mcu |
| `industrial_hmi_controller` | Industrial HMI controller | DRAFT | industrial_interfaces, emi_emc | 18 | mcu, buck_regulator, display_connector, tvs_diode |
| `relay_output_module` | Relay output module | DRAFT | mains_safety_isolation, industrial_interfaces | 26 | relay, relay_driver, flyback_diode, terminal_block |
| `current_loop_4_20ma_interface` | 4-20 mA loop interface | DRAFT | industrial_interfaces, precision_analog, galvanic_isolation | 23 | precision_resistor, tvs_diode, terminal_block |
| `din_rail_controller` | DIN-rail controller | DRAFT | industrial_interfaces, harsh_environment | 18 | mcu, buck_regulator, tvs_diode, terminal_block |

## LED lighting and display electronics (`led_display`, 5)

LED drivers, addressable LED controllers and display interfaces: constant-current regulation, thermal spreading and signal integrity to the panel.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `constant_current_led_driver` | Constant-current LED driver | DRAFT | switching_power, thermal_management | 31 | led_driver_dc, inductor, current_sense_resistor, led_emitter |
| `addressable_led_controller` | Addressable LED controller | DRAFT | high_current | 19 | mcu, level_shifter, bulk_capacitor, terminal_block |
| `lcd_tft_display_board` | LCD/TFT display board | DRAFT | high_speed_digital | 17 | display_connector, led_backlight_driver, mcu, decoupling_capacitor |
| `oled_epaper_display_board` | OLED / e-paper display board | DRAFT | low_power | 16 | display_connector, mcu, decoupling_capacitor |
| `led_backlight_driver` | LED backlight driver | DRAFT | switching_power, thermal_management | 29 | led_backlight_driver, inductor, schottky_diode, output_capacitor, input_capacitor |

## Testing, programming and debugging hardware (`test_debug`, 5)

Tools that connect to a target: programmers, analysers, fixtures and bench instruments, where protection of the target and signal fidelity matter.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `swd_jtag_programmer` | SWD/JTAG programmer-debugger | DRAFT | usb_interface | 17 | mcu, level_shifter, usb_connector, debug_header, esd_protection |
| `logic_analyzer_board` | Logic analyser board | DRAFT | usb_interface, high_speed_digital | 18 | mcu, esd_protection, usb_connector, pin_header |
| `bed_of_nails_test_fixture` | Bed-of-nails test fixture board | DRAFT |  | 15 | pogo_pin, mcu, pin_header |
| `benchtop_power_supply_control` | Bench power supply control board | DRAFT | precision_analog, thermal_management, high_current | 26 | mcu, dac, adc, voltage_reference, op_amp, current_sense_resistor, terminal_block |
| `signal_generator_board` | Signal generator board | DRAFT | precision_analog, high_speed_digital | 19 | dds_ic, op_amp, bnc_connector, mcu |

## Automotive and transportation electronics (`automotive`, 2)

12/24 V vehicle electronics: load dump, reverse battery, cold crank, CAN/LIN, and extended temperature with AEC-qualified parts.

| Archetype | Name | Maturity | Overlays | Rules | Required roles |
|---|---|---|---|---|---|
| `automotive_12v_controller` | Automotive 12 V controller | DRAFT | automotive_environment, can_interface, emi_emc, harsh_environment | 19 | mcu, automotive_buck_regulator, tvs_diode, automotive_connector, decoupling_capacitor |
| `obd_can_telematics` | OBD-II / CAN telematics device | DRAFT | automotive_environment, can_interface, rf_communication, emi_emc | 23 | mcu, can_transceiver, automotive_buck_regulator, tvs_diode, obd_connector |

## Overlays

| Overlay | Precedence | Applies when | Adds families | Rules |
|---|---|---|---|---|
| `rf_communication` | 60 | rf_frequency_hz > 1000000.0; protocols intersects ['wifi', 'ble', 'lora', 'lte', 'gnss', 'zigbee', 'uwb', 'subghz'] | antenna, rf_matching_component, esd_protection | PLACE-ANT-014, ROUTE-RF-022, ROUTE-RETURN-027, COPPER-ANT-045, EMI-RFHARM-064 |
| `high_current` | 70 | current_a >= 3.0 | bulk_capacitor, current_sense_resistor | ELEC-VIA-005, ELEC-DROP-006, ROUTE-POLY-026, PWR-ROUTE-170 |
| `thermal_management` | 50 | power_w >= 5.0; max_ambient_c >= 60 | heatsink, ntc_thermistor | PLACE-THERM-017, COPPER-THERMVIA-046, THERM-TJ-050, THERM-COPPER-051 |
| `emi_emc` | 55 | emc_class in ['A', 'B', 'industrial', 'automotive', 'medical']; switching_frequency_hz > 10000.0 | common_mode_choke, ferrite_bead, tvs_diode | EMI-FILTER-061 |
| `battery_management` | 65 | power_source intersects ['battery', 'solar']; cells >= 1 | battery_protection_ic, ntc_thermistor, battery_connector | ELEC-DROP-006, BAT-CHEM-130, BAT-PROT-131, BAT-NTC-132 |
| `low_power` | 30 | sleep_current_ua <= 100; battery_life_target exists True | load_switch |  |
| `usb_interface` | 40 | protocols intersects ['usb'] | usb_connector, esd_protection | ROUTE-DIFF-021, MCU-USB-102 |
| `mains_safety_isolation` | 100 | mains == True; input_voltage_v >= 60; isolation == True | fuse, mov_varistor, x_capacitor, y_capacitor | ELEC-CREEP-004, PLACE-ISO-016, ROUTE-HV-025, COPPER-BARRIER-044, MFG-COAT-073, MFG-SLOT-074, MAINS-DECL-160, MAINS-FUSE-161, MAINS-INS-163 |
| `galvanic_isolation` | 80 | isolation == True | digital_isolator, isolated_dc_dc_module | ELEC-CREEP-004, PLACE-ISO-016, ROUTE-HV-025, COPPER-BARRIER-044 |
| `industrial_interfaces` | 45 | protocols intersects ['rs485', 'can', 'modbus', 'profibus', 'ethercat']; input_voltage_v between [18, 36] | tvs_diode, terminal_block | ROUTE-DIFF-021, EMI-SURGE-063 |
| `high_speed_digital` | 50 | protocols intersects ['pcie', 'ddr', 'usb3', 'hdmi', 'mipi', 'sata', 'gigabit'] | clock_generator | ROUTE-DIFF-021, ROUTE-RETURN-027 |
| `precision_analog` | 45 | resolution_bits >= 14; signal_type in ['analog', 'sensor', 'audio'] | voltage_reference, ldo_regulator | PLACE-THERM-017, ROUTE-GUARD-030 |
| `motor_drive` | 60 | motor exists True | gate_driver, current_sense_resistor, dc_link_capacitor | ELEC-VIA-005, ELEC-DROP-006, ROUTE-POLY-026, ROUTE-GATE-028, ROUTE-ENC-029, COPPER-THERMVIA-046, THERM-TJ-050, MOTOR-PEAK-140, MOTOR-OC-141, PWR-ROUTE-170 |
| `can_interface` | 35 | protocols intersects ['can'] | can_transceiver, tvs_diode | ROUTE-DIFF-021 |
| `harsh_environment` | 30 | max_ambient_c >= 70; environment in ['outdoor', 'industrial', 'marine'] |  | MFG-COAT-073 |
| `automotive_environment` | 70 | power_source intersects ['vehicle'] | tvs_diode, automotive_buck_regulator | EMI-SURGE-063 |
| `switching_power` | 55 | converter exists True; switching_frequency_hz > 10000.0 | inductor, input_capacitor, output_capacitor | ELEC-VIA-005, ELEC-DROP-006, PLACE-HOTLOOP-012, PLACE-FB-013, ROUTE-SW-023, ROUTE-RETURN-027, ROUTE-GATE-028, COPPER-THERMVIA-046, THERM-TJ-050, EMI-LOOP-060, DCDC-VIN-121 |
