# Component family reference

206 families in 9 groups (generated from `library/pcb_domains/component_families/families.json`).
Families are roles, never part numbers: real parts come from `tools/resolve.py`, `library/devices.json` and `library/pins/`.

## Power components (`power`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `automotive_buck_regulator` | AEC-Q100 buck with 40 V+ input and low quiescent current. | input_voltage_range, output_voltage, output_current, aec_grade | Pin map from tools/pins.py against the real symbol; never from memory | Hot loop tight | 2 |
| `battery_monitor_afe` | Multi-cell voltage/temperature monitor with balancing and FET control. | cell_count, chemistry, balance_current, communication | Pin map from tools/pins.py against the real symbol; never from memory; Cell input series resistors | Cell taps in order; filters at the inputs | 2 |
| `battery_protection_ic` | Over-charge/discharge/current protection controlling series MOSFETs. | cell_count, chemistry, thresholds, discharge_current | Pin map from tools/pins.py against the real symbol; never from memory; Delay capacitors | MOSFETs in the pack negative path | 4 |
| `boost_regulator` | Step-up converter IC (integrated switch) with inductor at the input and rectifier at the output. | input_voltage_range, output_voltage, output_current, switching_frequency | Pin map from tools/pins.py against the real symbol; never from memory; Switch voltage rating vs output; Reference layout | Hot loop (switch, diode, Cout) minimal; Inductor at the SW pin | 2 |
| `brake_chopper` | IGBT/MOSFET and resistor dissipating regenerative energy. | bus_voltage, brake_power | Pin map from tools/pins.py against the real symbol; never from memory | Resistor off-board or heatsinked | 1 |
| `bridge_rectifier` | Full-wave rectifier for mains or AC inputs. | vrrm, if_average, ifsm | Pin map from tools/pins.py against the real symbol; never from memory | After the fuse/MOV | 7 |
| `buck_boost_regulator` | Four-switch or SEPIC converter regulating across a varying input. | input_voltage_range, output_voltage, output_current | Pin map from tools/pins.py against the real symbol; never from memory; Reference layout for both hot loops | Both switch nodes away from feedback | 2 |
| `buck_controller` | Controller driving external high-side/low-side MOSFETs for higher currents. | input_voltage_range, output_voltage, output_current, gate_drive_voltage | Pin map from tools/pins.py against the real symbol; never from memory; Dead-time and sense thresholds | Controller adjacent to the MOSFETs; gate loops short; Sense resistor Kelvin to the controller | 1 |
| `buck_regulator` | Step-down converter IC with an internal switch; needs inductor, capacitors and a feedback divider. | input_voltage_range, output_voltage, output_current, switching_frequency, inductor_value_range | Pin map from tools/pins.py against the real symbol; never from memory; Reference layout in the datasheet; Bootstrap and  | Hot loop (Cin, IC switch, catch diode/low-side) minimal; Feedback divider at the FB pin away from the switch node | 27 |
| `current_sense_amplifier` | Amplifies the voltage across a shunt at high common-mode voltage. | common_mode_range, gain, bandwidth | Pin map from tools/pins.py against the real symbol; never from memory | Near the shunt | 2 |
| `current_transformer` | AC current sensing with isolation. | ratio, burden_resistor | Pin map from tools/pins.py against the real symbol; never from memory | Near the measured conductor | 3 |
| `ddr_termination_regulator` | VTT/VREF regulator sourcing and sinking current for DDR termination. | ddr_type, vtt_current | Pin map from tools/pins.py against the real symbol; never from memory | At the termination resistors | 1 |
| `flyback_controller` | PWM controller for flyback converters (PSR or opto feedback). | input_voltage_range, output_power, regulation_method | Pin map from tools/pins.py against the real symbol; never from memory | Primary hot loop minimal | 2 |
| `flyback_diode` | Diode across inductive loads to clamp turn-off voltage. | current, voltage | Pin map from tools/pins.py against the real symbol; never from memory | At the load terminal | 3 |
| `fuel_gauge` | State-of-charge estimation via coulomb counting or impedance tracking. | chemistry, capacity_mah, sense_resistor | Pin map from tools/pins.py against the real symbol; never from memory | Shunt adjacent with Kelvin sense | 3 |
| `gate_driver` | Half-bridge or single gate driver with level shifting, bootstrap or isolation. | drive_voltage, peak_current, dead_time, isolation_rating | Pin map from tools/pins.py against the real symbol; never from memory; Bootstrap diode requirement; Dead-time setting | Adjacent to the MOSFETs; bootstrap cap at the driver | 8 |
| `h_bridge_driver` | Integrated full bridge for brushed DC motors or bipolar loads. | supply_voltage, peak_current, pwm_frequency | Pin map from tools/pins.py against the real symbol; never from memory; Thermal pad | Bulk capacitor at the supply pins | 2 |
| `hall_current_sensor` | Isolated current sensor with a Hall element. | current_range, isolation_rating | Pin map from tools/pins.py against the real symbol; never from memory | Primary path through the sensor | 1 |
| `high_side_switch` | Protected high-side driver with diagnostics for 12/24 V loads. | load_current, supply_voltage | Pin map from tools/pins.py against the real symbol; never from memory | Near the output terminal | 4 |
| `hv_buck_regulator` | Offline buck IC with an internal HV switch for mA-level mains supplies. | input_voltage_range, output_voltage, output_current | Pin map from tools/pins.py against the real symbol; never from memory; Creepage of the package itself | Mains creepage around every pin and trace | 1 |
| `ideal_diode_controller` | Controls a MOSFET to emulate a low-drop diode for OR-ing and reverse protection. | input_voltage, load_current | Pin map from tools/pins.py against the real symbol; never from memory | Adjacent to the MOSFET | 1 |
| `igbt` | Insulated-gate bipolar transistor for high-voltage bridges and inverters. | vce_rating, ic_continuous, vce_sat, switching_energy | Pin map from tools/pins.py against the real symbol; never from memory | Module or discrete with heatsink interface | 3 |
| `ipm_module` | Integrated three-phase inverter with gate drivers and protection. | bus_voltage, phase_current, switching_frequency | Pin map from tools/pins.py against the real symbol; never from memory | Heatsink mounting; shunt Kelvin | 1 |
| `isolated_dc_dc_module` | Encapsulated isolated converter for isolated supplies. | isolation_rating, input_voltage, output_voltage, output_power | Pin map from tools/pins.py against the real symbol; never from memory | Straddles the barrier | 8 |
| `isolated_gate_driver` | Gate driver with galvanic isolation for high-side or HV devices. | isolation_rating, drive_voltage, peak_current, cmti | Pin map from tools/pins.py against the real symbol; never from memory; Isolation working voltage | Straddles the barrier; isolated supply adjacent | 1 |
| `ldo_regulator` | Low-dropout linear regulator for clean, low-current rails. | input_voltage_range, output_voltage, output_current, dropout_voltage, thermal_resistance | Pin map from tools/pins.py against the real symbol; never from memory; Stability note for ceramic output capacitors; The | Input and output capacitors adjacent to the pins; Thermal pad vias to a copper area for > 0.3 W | 36 |
| `led_backlight_driver` | Multi-string boost LED driver with current sinks. | string_count, string_voltage, string_current | Pin map from tools/pins.py against the real symbol; never from memory | Boost loop tight | 3 |
| `led_driver_dc` | Buck/boost constant-current LED driver. | input_voltage_range, string_voltage, string_current | Pin map from tools/pins.py against the real symbol; never from memory | Hot loop tight | 1 |
| `led_driver_offline` | Mains LED driver controller (isolated or non-isolated). | input_voltage_range, string_voltage, string_current, isolation | Pin map from tools/pins.py against the real symbol; never from memory | Barrier rules | 1 |
| `li_ion_charger` | CC/CV charger for single-cell lithium batteries. | input_voltage_range, charge_current, charge_voltage, chemistry | Pin map from tools/pins.py against the real symbol; never from memory; Thermal pad; NTC resistor values | Copper area for dissipation; NTC at the cell | 4 |
| `load_switch` | Controlled power switch with soft start and optional current limit. | input_voltage, load_current, slew_rate | Pin map from tools/pins.py against the real symbol; never from memory | Near the controlled rail | 10 |
| `low_side_switch` | MOSFET or integrated low-side driver for inductive and resistive loads. | load_current, load_voltage | Pin map from tools/pins.py against the real symbol; never from memory | Flyback diode at the load terminal | 2 |
| `mosfet` | N/P-channel switch for converters, bridges and load switching. | vds_rating, id_continuous, rds_on, qg, package_thermal_resistance | Pin map from tools/pins.py against the real symbol; never from memory; Rds(on) at the actual gate voltage; Thermal resis | Adjacent to the driver; exposed pad with via array | 29 |
| `mosfet_sr` | Low-voltage, low-Rds(on) MOSFET replacing the output diode in isolated converters. | vds_rating, id_continuous, rds_on | Pin map from tools/pins.py against the real symbol; never from memory | Adjacent to the transformer secondary and Cout | 2 |
| `mppt_charge_controller` | Solar charge controller IC or MCU-based MPPT with a DC-DC stage. | pv_voc_max, battery_voltage, charge_current, chemistry | Pin map from tools/pins.py against the real symbol; never from memory | Input protection at the PV terminals | 1 |
| `opto_triac_driver` | Optically isolated triac trigger (zero-cross or random). | isolation_rating, trigger_type | Pin map from tools/pins.py against the real symbol; never from memory | On the barrier | 1 |
| `pfc_controller` | Boost PFC controller (CrM/CCM/interleaved). | input_voltage_range, bus_voltage, output_power | Pin map from tools/pins.py against the real symbol; never from memory | Near the boost switch | 1 |
| `pmic_power_path` | Integrated charger, power-path and regulators for battery products. | input_voltage_range, system_current, charge_current, chemistry | Pin map from tools/pins.py against the real symbol; never from memory; Thermal regulation | Thermal pad; capacitors at the pins | 1 |
| `poe_pd_controller` | Powered-device interface: detection, classification, inrush and isolated converter control. | poe_class, output_power | Pin map from tools/pins.py against the real symbol; never from memory | Near the bridge rectifiers | 1 |
| `power_monitor_ic` | Digital current/voltage/power monitor over I2C. | shunt_resistance, bus_voltage_max | Pin map from tools/pins.py against the real symbol; never from memory | Near the shunt | 1 |
| `power_sequencer` | Sequences and monitors multiple rails. | rail_count, sequence_order | Pin map from tools/pins.py against the real symbol; never from memory | Central to the regulators | 2 |
| `pwm_controller` | General PWM/resonant controller for isolated topologies. | topology, frequency, output_power | Pin map from tools/pins.py against the real symbol; never from memory | Near the primary switches | 4 |
| `rectifier_diode` | Fast or standard rectifiers for secondary sides. | vrrm, if_average | Pin map from tools/pins.py against the real symbol; never from memory | Secondary loop | 3 |
| `relay_driver` | Transistor array or driver IC for relay coils with clamps. | coil_current, coil_voltage | Pin map from tools/pins.py against the real symbol; never from memory | Near the relays | 1 |
| `schottky_diode` | Low-forward-drop rectifier for converters and reverse protection. | vrrm, if_average | Pin map from tools/pins.py against the real symbol; never from memory | In the hot loop | 9 |
| `sic_diode` | Zero-recovery diode for PFC and HV converters. | vrrm, if_average | Pin map from tools/pins.py against the real symbol; never from memory | Hot loop | 1 |
| `solar_charge_controller` | Simple PWM solar charger for small systems. | pv_voc_max, battery_voltage, charge_current | Pin map from tools/pins.py against the real symbol; never from memory | Diode or ideal diode at the panel | 0 |
| `ssr` | Optically isolated semiconductor switch for AC/DC loads. | load_current, load_voltage, isolation_rating | Pin map from tools/pins.py against the real symbol; never from memory | Barrier | 1 |
| `stepper_driver_ic` | Dual H-bridge with current chopping and microstepping. | supply_voltage, phase_current, microstep_mode | Pin map from tools/pins.py against the real symbol; never from memory; Thermal pad | Thermal pad vias; sense resistors Kelvin | 1 |
| `switching_charger` | Buck or buck-boost charger for 1-6 cells with input current limiting. | input_voltage_range, cell_count, charge_current, chemistry | Pin map from tools/pins.py against the real symbol; never from memory | Hot loop per topology; Kelvin sense | 1 |
| `three_phase_gate_driver` | Driver for three half-bridges with current-sense amplifiers and fault logic. | drive_voltage, peak_current, csa_gain, fault_thresholds | Pin map from tools/pins.py against the real symbol; never from memory; Reference layout; Dead time | Central to the three half-bridges | 2 |
| `triac` | Bidirectional thyristor for AC load switching. | vdrm, it_rms, igt | Pin map from tools/pins.py against the real symbol; never from memory | Heatsink interface | 1 |

## Passive components (`passive`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `balancing_resistor` | Bleed resistor for passive balancing. | value, power_rating |  | Spread for heat | 2 |
| `boost_inductor_pfc` | Large inductor for PFC stages. | inductance, isat |  | Hot loop | 1 |
| `bootstrap_capacitor` | Capacitor supplying the high-side gate driver. | value, voltage_rating | Driver datasheet | At the driver BST pin | 1 |
| `bulk_capacitor` | Electrolytic/polymer reservoir for peak currents. | value, voltage_rating, ripple_current | Ripple and lifetime | Near the load's supply pins | 11 |
| `common_mode_choke` | Filters common-mode noise on power or signal pairs. | impedance, current_rating | Safety for mains | At the entry | 5 |
| `coupled_inductor` | Dual-winding inductor for SEPIC/Zeta. | inductance, isat |  | Near the switch | 1 |
| `crystal` | Quartz resonator for MCU/RF clocks. | frequency, load_capacitance, tolerance | Drive level | Within 5 mm of the pins; no traces under | 14 |
| `current_sense_resistor` | Low-value shunt with Kelvin pads. | value, power_rating, tolerance | Kelvin footprint | In the measured path | 19 |
| `dc_link_capacitor` | Film or electrolytic bank across a bridge's DC bus. | value, voltage_rating, ripple_current | Ripple | Tight to the bridge switches | 5 |
| `decoupling_capacitor` | MLCC at supply pins providing local charge. | value, voltage_rating, dielectric | Value per the IC datasheet | At the pin, smallest closest | 47 |
| `discharge_resistor` | Bleeder across X capacitors. | value, power_rating |  | Across the X cap | 2 |
| `feedback_resistor` | Divider setting a converter's output. | value, tolerance |  | At the FB pin | 3 |
| `ferrite_bead` | Impedance element for supply filtering. | impedance, current_rating |  | Between rails | 6 |
| `film_capacitor` | Low-distortion capacitor for audio and filters. | value, voltage_rating |  | In the filter | 6 |
| `gate_resistor` | Series resistor shaping the gate drive edge. | value |  | At the driver output | 1 |
| `inductor` | Energy-storage inductor for converters. | inductance, isat, dcr | Isat vs temperature | At the SW pin | 10 |
| `input_capacitor` | Ceramic/electrolytic at a converter input carrying the ripple current. | value, voltage_rating, ripple_current | Ripple current spec | In the hot loop | 13 |
| `mov_varistor` | Metal-oxide varistor clamping surges. | varistor_voltage, energy | Thermal fuse if required | After the fuse | 5 |
| `ntc_inrush_limiter` | Power thermistor limiting mains inrush. | r25, max_current |  | In series after the fuse | 3 |
| `ntc_thermistor` | Temperature sensing element (battery/charger). | r25, beta |  | At the measured object | 8 |
| `output_capacitor` | Output filter capacitor setting ripple and loop response. | value, voltage_rating, esr | Stability note | At the inductor output | 17 |
| `output_inductor` | Filter inductor in forward/half-bridge outputs or class-D filters. | inductance, isat |  | At the rectifier/amplifier output | 4 |
| `potentiometer` | Variable resistor for volume/trim. | value |  | Accessible | 1 |
| `power_resistor` | Series/dropper/bleeder resistor dissipating continuously. | value, power_rating, voltage_rating |  | Away from heat-sensitive parts | 1 |
| `precision_resistor` | Thin-film resistor for references, dividers and sense. | value, tolerance, tempco |  | Away from heat | 11 |
| `rcd_clamp` | Resistor-capacitor-diode clamp for flyback leakage spikes. | clamp_voltage, power |  | At the transformer primary | 1 |
| `resonant_capacitor` | Film capacitor in LLC tanks with high ripple current. | value, voltage_rating, ripple_current |  | In the tank | 1 |
| `resonant_inductor` | Series inductor in LLC/DAB tanks. | inductance, isat |  | In the tank | 2 |
| `snubber_rc` | Damping network across switches or contacts. | resistance, capacitance |  | At the switch node | 2 |
| `supercapacitor` | High-capacitance reservoir for pulses and backup. | capacitance, voltage_rating, esr | Leakage | Near the pulse load | 4 |
| `x_capacitor` | Safety-rated capacitor across the mains lines. | value, safety_class | Safety approval | After the fuse | 3 |
| `y_capacitor` | Safety-rated capacitor across the isolation barrier or to earth. | value, safety_class | Safety approval | Across the barrier only | 4 |

## Digital components (`digital`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `audio_codec` | ADC/DAC with I2S. | sample_rates, interface | Pin map from tools/pins.py against the real symbol; never from memory | Analog partition | 2 |
| `audio_dac` | I2S DAC. | resolution, interface | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `cellular_module` | LTE/NB-IoT modem module. | bands, io_voltage | Pin map from tools/pins.py against the real symbol; never from memory; Layout guide | Bulk caps adjacent | 2 |
| `class_d_amplifier_ic` | Switching audio amplifier. | supply_voltage, output_power, load_impedance | Pin map from tools/pins.py against the real symbol; never from memory | Filter at pins | 1 |
| `clock_generator` | Oscillators and PLL clock generators. | frequency, jitter, output_type | Pin map from tools/pins.py against the real symbol; never from memory | Central to loads | 7 |
| `configuration_flash` | SPI/QSPI flash for FPGA/MCU configuration. | size, interface | Pin map from tools/pins.py against the real symbol; never from memory | Near the controller | 1 |
| `ddr_memory` | SDRAM for processors/FPGAs. | type, width, speed_grade | Pin map from tools/pins.py against the real symbol; never from memory; Topology | Near the controller | 2 |
| `dds_ic` | Direct digital synthesis IC for waveform generation. | clock_frequency, output_frequency_max | Pin map from tools/pins.py against the real symbol; never from memory | Near the clock and DAC filter | 1 |
| `eeprom_flash` | Small non-volatile memory. | size, interface | Pin map from tools/pins.py against the real symbol; never from memory | Near the host | 0 |
| `encoder_interface` | ABZ/SSI/BiSS receiver logic. | type | Pin map from tools/pins.py against the real symbol; never from memory |  | 3 |
| `ethernet_phy` | 10/100/1000 PHY. | speed, host_interface | Pin map from tools/pins.py against the real symbol; never from memory | Near magnetics | 5 |
| `fpga` | Programmable logic device. | family, package, io_standards | Pin map from tools/pins.py against the real symbol; never from memory; Sequencing | Decoupling per guide | 5 |
| `gnss_module` | GPS/GNSS receiver module. | constellations, antenna_type | Pin map from tools/pins.py against the real symbol; never from memory | RF path | 2 |
| `gpio_expander` | I2C/SPI port expander. | interface, channels | Pin map from tools/pins.py against the real symbol; never from memory | Near the loads | 1 |
| `hall_sensor_interface` | Pull-ups/filters for motor hall sensors. | count |  |  | 1 |
| `hdmi_level_shifter` | TMDS buffer. | data_rate | Pin map from tools/pins.py against the real symbol; never from memory | Near the connector | 1 |
| `high_speed_adc` | MSPS-GSPS converter. | sample_rate, resolution, interface | Pin map from tools/pins.py against the real symbol; never from memory | Analog/digital partition | 1 |
| `high_speed_dac` | MSPS-GSPS DAC. | sample_rate, resolution | Pin map from tools/pins.py against the real symbol; never from memory | Partition | 2 |
| `i2c_multiplexer` | Bus switch for address conflicts. | channels | Pin map from tools/pins.py against the real symbol; never from memory |  | 3 |
| `image_sensor` | CMOS image sensor with MIPI/parallel output. | resolution, interface | Pin map from tools/pins.py against the real symbol; never from memory | Under the lens datum | 1 |
| `level_shifter` | Voltage translation between logic domains. | voltage_a, voltage_b, speed | Pin map from tools/pins.py against the real symbol; never from memory | Between domains | 8 |
| `loop_transmitter_ic` | Loop-powered transmitter. | loop_voltage | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `magnetic_encoder_ic` | Hall-based angle sensor. | resolution, interface | Pin map from tools/pins.py against the real symbol; never from memory | Centred on the magnet axis | 1 |
| `mcu` | General MCU running the application. | core, flash, io_voltage, interfaces | Pin map from tools/pins.py against the real symbol; never from memory; Strap pins; Decoupling table | Central; decoupling at pins; crystal adjacent | 48 |
| `mcu_wireless_module` | Certified module with MCU and radio (ESP32, nRF, etc.). | module, antenna_type, interfaces | Pin map from tools/pins.py against the real symbol; never from memory; Antenna keep-out | Antenna at edge with keep-out | 5 |
| `pcie_endpoint` | Device-side PCIe silicon. | generation, lanes | Pin map from tools/pins.py against the real symbol; never from memory | Near the edge | 2 |
| `qspi_flash` | External program/storage flash. | size, interface_speed | Pin map from tools/pins.py against the real symbol; never from memory | Adjacent | 1 |
| `resolver_to_digital` | Resolver excitation and demodulation. | resolution | Pin map from tools/pins.py against the real symbol; never from memory | Near connector | 1 |
| `rtc` | Timekeeping IC with backup supply. | interface, backup_source | Pin map from tools/pins.py against the real symbol; never from memory | Crystal adjacent | 3 |
| `touch_controller` | Capacitive touch panel controller. | interface | Pin map from tools/pins.py against the real symbol; never from memory | Near the FPC | 2 |
| `usb_hub_controller` | Multi-port hub IC. | ports, speed | Pin map from tools/pins.py against the real symbol; never from memory | Central | 2 |
| `usb_mux` | High-speed mux for orientation/alt modes. | lanes | Pin map from tools/pins.py against the real symbol; never from memory | Near the connector | 1 |
| `usb_pd_controller` | CC negotiation controller. | role, pdos | Pin map from tools/pins.py against the real symbol; never from memory | Near CC pins | 2 |
| `usb_uart_bridge` | USB to serial converter IC. | interface | Pin map from tools/pins.py against the real symbol; never from memory | Near the USB connector | 1 |

## RF components (`rf`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `antenna` | PCB trace, chip or external antenna. | band, type, keepout_mm | Keep-out drawing | Board edge with keep-out | 10 |
| `balun` | Balanced-unbalanced transformer. | band, impedance_ratio | Pin map from tools/pins.py against the real symbol; never from memory | At the transceiver | 3 |
| `directional_coupler` | Forward/reflected sampling. | band, coupling_db |  | Symmetric | 1 |
| `lna` | Receive-path amplifier. | band, noise_figure | Pin map from tools/pins.py against the real symbol; never from memory | At the antenna port | 3 |
| `power_amplifier` | PA for transmit paths. | band, output_power | Pin map from tools/pins.py against the real symbol; never from memory | Thermal vias | 1 |
| `rf_attenuator` | Fixed/variable attenuation. | attenuation_db, power_rating |  |  | 2 |
| `rf_connector` | u.FL/SMA/MMCX. | type, frequency_max |  | At the edge | 8 |
| `rf_detector` | Log/RMS detector IC. | band, dynamic_range | Pin map from tools/pins.py against the real symbol; never from memory | Near the coupler | 1 |
| `rf_matching_component` | 0402/0201 L/C in pi networks. | value, tolerance |  | Inline between port and antenna | 6 |
| `rf_switch` | SPDT/SPnT RF switch. | band, power_handling | Pin map from tools/pins.py against the real symbol; never from memory | Between PA/LNA and antenna | 3 |
| `rf_test_connector` | Measurement port. | type |  | Inline | 1 |
| `rf_transceiver` | Radio transceiver IC (sub-GHz, 2.4 GHz, UWB, wideband). | band, output_power, interface | Pin map from tools/pins.py against the real symbol; never from memory; Reference design | Near the antenna; crystal adjacent | 6 |
| `saw_filter` | Band filter. | band | Pin map from tools/pins.py against the real symbol; never from memory | In the RF path | 3 |

## Analog components (`analog`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `adc` | Precision or general ADC. | resolution, sample_rate, reference | Pin map from tools/pins.py against the real symbol; never from memory | Reference adjacent; partition | 9 |
| `analog_switch` | Signal routing. | channels, ron | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `bridge_adc` | ADC with integrated PGA for load cells. | gain, resolution | Pin map from tools/pins.py against the real symbol; never from memory | Near the terminals | 1 |
| `comparator` | Threshold detection. | propagation_delay | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `dac` | Precision DAC. | resolution, reference | Pin map from tools/pins.py against the real symbol; never from memory |  | 2 |
| `headphone_driver` | Dedicated headphone amplifier. | load_impedance, output_power | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `instrumentation_amplifier` | High-CMRR differential amplifier. | gain, cmrr | Pin map from tools/pins.py against the real symbol; never from memory | Near the inputs | 3 |
| `isolated_adc` | Delta-sigma modulator across a barrier. | isolation_rating, resolution | Pin map from tools/pins.py against the real symbol; never from memory | On the barrier | 1 |
| `isolated_amplifier` | Amplifier across a barrier. | isolation_rating, gain | Pin map from tools/pins.py against the real symbol; never from memory | On the barrier | 1 |
| `op_amp` | General/precision op-amp. | gbw, input_bias_current, offset, supply_range | Pin map from tools/pins.py against the real symbol; never from memory | Near the source | 11 |
| `potentiostat_afe` | Electrochemical front end. | electrodes | Pin map from tools/pins.py against the real symbol; never from memory | Guarded | 1 |
| `rtd_converter` | Ratiometric RTD front end. | rtd_type, wires | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `shunt_reference` | Adjustable shunt for feedback. | reference_voltage | Pin map from tools/pins.py against the real symbol; never from memory | Secondary side | 3 |
| `thermocouple_converter` | Cold-junction-compensated converter. | thermocouple_type | Pin map from tools/pins.py against the real symbol; never from memory | At the terminals | 1 |
| `voltage_reference` | Precision reference. | voltage, drift, noise | Pin map from tools/pins.py against the real symbol; never from memory | Away from heat; decoupled | 11 |
| `voltage_sense_divider` | Resistor string scaling HV to ADC range. | ratio, voltage |  | Creepage along the string | 4 |

## Interfaces and protection (`interface_protection`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `can_transceiver` | ISO 11898-2 transceiver. | bit_rate, supply | Pin map from tools/pins.py against the real symbol; never from memory | Near the connector | 9 |
| `desat_diode` | HV diode for desaturation detection. | voltage |  | Near the driver | 1 |
| `digital_isolator` | Capacitive/magnetic isolator. | isolation_rating, channels, data_rate | Pin map from tools/pins.py against the real symbol; never from memory | On the barrier | 11 |
| `esd_protection` | Low-capacitance ESD diode array. | channels, capacitance, working_voltage | Pin map from tools/pins.py against the real symbol; never from memory | At the connector | 30 |
| `fuse` | Overcurrent protection. | current_rating, voltage_rating, type | Safety approval for mains | First after the input | 9 |
| `gdt` | High-energy surge arrester. | sparkover_voltage |  | At the entry | 2 |
| `i2c_isolator` | Bidirectional isolator. | isolation_rating | Pin map from tools/pins.py against the real symbol; never from memory | Barrier | 1 |
| `kline_transceiver` | ISO 9141 K-line interface. | supply | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `lin_transceiver` | LIN bus transceiver. | supply | Pin map from tools/pins.py against the real symbol; never from memory | Near connector | 1 |
| `optocoupler` | Optical isolator for feedback/inputs. | isolation_rating, ctr | Pin map from tools/pins.py against the real symbol; never from memory | Barrier | 9 |
| `rs422_receiver` | Differential receiver for encoders. | channels | Pin map from tools/pins.py against the real symbol; never from memory |  | 2 |
| `rs485_transceiver` | TIA-485 driver/receiver. | bit_rate, supply | Pin map from tools/pins.py against the real symbol; never from memory | Near the terminals | 4 |
| `tvs_diode` | Surge clamp. | working_voltage, peak_power |  | At the entry | 26 |
| `zener_diode` | Voltage clamp/regulator. | voltage, power |  |  | 1 |

## Sensors and actuators (`sensor_actuator`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `environmental_sensor` | Temperature/humidity/pressure sensor. | type, interface | Pin map from tools/pins.py against the real symbol; never from memory | Thermally isolated | 4 |
| `gas_sensor` | Metal-oxide/electrochemical gas sensor. | gas, heater_current | Pin map from tools/pins.py against the real symbol; never from memory | Vented | 1 |
| `haptic_driver` | LRA/ERM driver. | actuator_type | Pin map from tools/pins.py against the real symbol; never from memory |  | 1 |
| `imu` | Accelerometer/gyroscope. | axes, interface | Pin map from tools/pins.py against the real symbol; never from memory | Rigid area | 3 |
| `light_sensor` | Ambient light sensor. | interface | Pin map from tools/pins.py against the real symbol; never from memory | Window | 1 |
| `magnetometer` | Magnetic field sensor. | interface | Pin map from tools/pins.py against the real symbol; never from memory | Away from current | 1 |
| `mems_microphone` | PDM/I2S microphone. | interface | Pin map from tools/pins.py against the real symbol; never from memory | Port hole | 1 |
| `optical_sensor` | LED+photodiode AFE. | interface | Pin map from tools/pins.py against the real symbol; never from memory | Window | 1 |
| `photodiode` | Light-to-current sensor. | wavelength, capacitance |  | Adjacent to the TIA | 1 |
| `zero_cross_detector` | Mains zero-cross sensing (isolated). | isolation_rating | Pin map from tools/pins.py against the real symbol; never from memory | Barrier | 1 |

## Electromechanical and connectors (`electromechanical`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `audio_jack` | 3.5 mm jack. | type |  | Edge | 3 |
| `automotive_connector` | Sealed vehicle connector. | pins, current_rating |  | Edge | 1 |
| `battery_connector` | JST/pack connector. | current_rating |  | Edge | 6 |
| `bnc_connector` | BNC for instruments. | type |  | Edge | 2 |
| `board_to_board_connector` | Mezzanine/edge connector. | pins, pitch, stack_height | Drawing |  | 3 |
| `card_edge_connector` | PCIe/M.2 gold fingers. | spec | CEM/M.2 drawing | Edge | 1 |
| `cell_tap_connector` | Multi-pin balance connector. | pins |  |  | 1 |
| `coin_cell_holder` | CR2032 holder. | cell |  |  | 3 |
| `debug_header` | SWD/JTAG header. | pinout |  | Accessible | 3 |
| `display_connector` | FPC/ZIF for panels. | pins, pitch | Drawing |  | 5 |
| `ethernet_magnetics` | Isolation transformers for Ethernet. | speed, poe |  | Between PHY and jack | 3 |
| `fan_connector` | 2/3/4-pin fan header. | pins |  |  | 1 |
| `flyback_transformer` | Coupled inductor for flyback. | primary_inductance, turns_ratio, isolation_rating | Safety rating | Barrier | 5 |
| `hdmi_connector` | HDMI receptacle. | type | Drawing | Edge | 1 |
| `heatsink` | Thermal interface. | thermal_resistance |  | Mounting holes | 4 |
| `high_speed_connector` | FMC/PCIe/SFP class connector. | type | Drawing | Edge | 1 |
| `m2_connector` | M.2 key socket. | key |  |  | 1 |
| `mains_connector` | IEC/terminal mains entry. | current_rating |  | Edge | 3 |
| `mipi_connector` | Camera/display FPC. | pins, pitch | Drawing |  | 2 |
| `motor_connector` | Phase connector. | current_rating |  | Near the bridge | 4 |
| `obd_connector` | SAE J1962 plug. | type |  |  | 1 |
| `pin_header` | 0.1 in headers. | pins |  |  | 4 |
| `pogo_pin` | Spring probe. | current_rating, travel |  | At the test-point coordinates | 1 |
| `power_transformer` | Isolated converter transformer. | turns_ratio, isolation_rating, power | Safety rating | Barrier | 5 |
| `relay` | Electromechanical relay. | coil_voltage, contact_rating | Approval for mains | Near terminals | 5 |
| `rj45_connector` | Ethernet jack (with/without magnetics). | magnetics_integrated | Drawing | Edge | 4 |
| `sd_card_socket` | microSD/SD socket. | type |  |  | 2 |
| `sim_holder` | Nano-SIM/eSIM. | type |  | Near module | 1 |
| `speaker_connector` | Speaker terminals. | current_rating |  |  | 1 |
| `tactile_switch` | Push button. | type |  | Accessible | 3 |
| `terminal_block` | Screw/push-in terminals. | current_rating, pitch |  | Edge | 16 |
| `usb_c_connector` | Type-C receptacle. | type, current_rating | Drawing | Edge | 2 |
| `usb_connector` | USB-A/B/micro. | type |  | Edge | 13 |

## Display and optical (`display_optical`)

| Family | Description | Required parameters | Datasheet checks | Placement | Used by |
|---|---|---|---|---|---|
| `led_emitter` | Illumination/indicator LED. | forward_current, forward_voltage |  | Thermal vias | 2 |
| `led_indicator` | Status LED with resistor. | colour |  | Visible | 4 |

