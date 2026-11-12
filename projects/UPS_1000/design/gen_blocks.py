"""UPS_1000 rev A (LV prototype) block-spec source. Generates projects/UPS_1000/blocks/NN_ID.json.

This is the single source of the schematic: every part, pin->net map (pin numbers from library/pins/<MPN>.json,
probed live by tools/pins.py) and qa[] derivation lives here. Datasheet citations refer to
live-test/ups-1000/requirements/DATASHEET_FACTS.md (page = PDF page). Designators are assigned in order.
Run: python projects/UPS_1000/design/gen_blocks.py
"""
import json, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "blocks")
LIB = json.load(open(os.path.join(HERE, "..", "..", "..", "library", "devices.json"), encoding="utf-8"))
DS = "live-test/ups-1000/requirements/DATASHEET_FACTS.md"
counters = {}


def ref(prefix):
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}{counters[prefix]}"


PKG = {"R0603": "0603", "C0603": "0603", "C1206": "1206", "C1210": "1210", "C0805": "0805", "R2512": "2512"}


def part(prefix, mpn, role, pins, nc=(), value=None, rating=None):
    d = LIB[mpn]
    p = {"ref": ref(prefix), "mpn": mpn, "role": role, "pins": {str(k): v for k, v in pins.items()},
         "nc": [str(x) for x in nc], "lcsc": d.get("lcsc") or "", "package": PKG.get(d.get("footprint"), d.get("footprint") or "")}
    if value:
        p["value"] = value
    if rating:
        p["rating"] = rating
    return p


def R(mpn, value, a, b, role, rating="1% 0.1W 75V"):
    return part("R", mpn, role, {1: a, 2: b}, value=value, rating=rating)


def C(mpn, value, a, b, role, rating):
    return part("C", mpn, role, {1: a, 2: b}, value=value, rating=rating)


R10, R22, R100, R120, R1K, R4K7, R5K1, R10K, R20K, R40K2, R75K, R91K, R100K, R110K = (
    "0603WAF100JT5E", "0603WAF220JT5E", "0603WAF1000T5E", "0603WAF1200T5E", "0603WAF1001T5E", "0603WAF4701T5E",
    "0603WAF5101T5E", "0603WAF1002T5E", "0603WAF2002T5E", "0603WAF4022T5E", "0603WAF7502T5E", "0603WAF9102T5E",
    "0603WAF1003T5E", "0603WAF1103T5E")
C100N, C100N100V, C1U, C1U100V, C2U2_100V, C4U7, C10U25, C22U25, C1N, C2N2, C10N, C30P, CBULK = (
    "CL10B104KB8NNNC", "CL10B104KC8NNNC", "CL10A105KB8NNNC", "CL31B105KCHNNNE", "CL32B225KCJSNNE", "CL10A475KO8NNNC",
    "CL21A106KAYNNNE", "CL31A226KAHNNNE", "CL10B102KB8NNNC", "CL10B222KB8NNNC", "CL10B103KB8NNNC", "CL10C300JB8NNNC",
    "MAL214099812E3")


def qa(item, formula, result, limit, source, ok=True):
    return {"item": item, "formula": formula, "result": result, "limit": limit, "source": source, "pass": ok}


blocks = []


def block(bid, title, purpose, ports, parts, qas):
    blocks.append({"id": bid, "title": title, "status": "draft", "purpose": purpose, "ports": ports,
                   "parts": parts, "qa": qas})


# ---------------------------------------------------------------- 01 POWER INPUT
vs_ratio = 5.1 / (100 + 5.1)
block("01_PWR_IN", "POWER INPUT AND PROTECTION",
      "Current-limited lab DC input (20-58.4 V, bring-up 24 V): fuse, TVS clamp (reverse polarity NOT fully protected: RK-01), bulk capacitance and VBUS sense divider. SELV only; no mains.",
      ["VBUS", "VBUS_SNS", "GND"],
      [part("J", "WJ128V-5.0-02P-14-00A", "Lab DC input terminal 5.0 mm, pin1 VIN+, pin2 GND", {1: "VIN_RAW", 2: "GND"}),
       part("F", "0451007.MRL", "7 A fast fuse in series with VIN+ (first element after J1)", {1: "VIN_RAW", 2: "VBUS"}, value="7A", rating="125V 7A fast"),
       part("D", "SMBJ60A", "TVS VBUS clamp (reverse-polarity protection only if supply current exceeds F1 rating, see RK-01)", {1: "VBUS", 2: "GND"}, rating="VRWM 60V VC 96.8V"),
       C(CBULK, "100uF", "VBUS", "GND", "VBUS bulk electrolytic #1 (pin1 = +, verify on footprint)", "100V Al 12.5mm"),
       C(CBULK, "100uF", "VBUS", "GND", "VBUS bulk electrolytic #2 (pin1 = +, verify on footprint)", "100V Al 12.5mm"),
       C(C1U100V, "1uF", "VBUS", "GND", "VBUS HF ceramic at input", "100V X7R 1206"),
       R(R100K, "100k", "VBUS", "VBUS_SNS", "VBUS sense divider top"),
       R(R5K1, "5.1k", "VBUS_SNS", "GND", "VBUS sense divider bottom"),
       C(C100N, "100nF", "VBUS_SNS", "GND", "VBUS_SNS ADC/comparator filter cap", "50V X7R")],
      [qa("VBUS_SNS scale", "Vs = VBUS*5.1k/(100k+5.1k)", f"{vs_ratio:.5f} V/V; 58.4 V -> {58.4*vs_ratio:.3f} V; 60 V -> {60*vs_ratio:.3f} V", "< 3.3 V ADC full scale", "calc"),
       qa("Divider dissipation", "P = V^2/R", f"{60**2/105.1e3*1e3:.1f} mW at 60 V in R 100k 0603", "<= 100 mW (0603 0.1 W), 75 V element rating", "UniOhm 0603WAF series rating"),
       qa("TVS standoff vs max operating", "VRWM >= VBUS_max", "60.0 V >= 58.4 V", "no conduction in operation", f"{DS} SMBJ60A p2"),
       qa("TVS clamp vs 100 V parts", "VC(IPP) <= VDS(Q) / VIN_abs(LM5164)", "96.8 V vs 100 V (3% margin at full IPP 6.2 A); INA240 CM ROC 80 V is BELOW clamp -> risk only under surge, lab supply only", "documented risk", f"{DS} SMBJ60A p2, INA240 s7.3 p4", True),
       qa("Fuse rating", "I_fuse >= 1.25 x I_cont_in; I_cont_in <= lab CL 6 A", "7 A >= 1.25 x 5 A RMS load. Reverse polarity: NOT protected when lab CL (<=6 A) < fuse rating - see REQUIREMENTS RK-01", "Littelfuse 451 7 A fast", "builder calc; fuse datasheet TO VERIFY (littelfuse.com 403)", True),
       qa("Bulk cap ripple", "Icin_rms ~= Io*sqrt(D(1-D)) = 5*0.5", "2.5 A RMS shared by 3x2.2uF MLCC (block 07) + 2x100uF Al", "Al ripple rating TO VERIFY from Vishay 140 CRH datasheet", "calc", True),
       qa("Bulk cap voltage derating", "V_op/V_rated", "58.4/100 = 58 %", "<= 80 %", "calc")])

# ---------------------------------------------------------------- 02 AUX 12 V
vout12 = 1.2 * (1 + 91 / 10)
fsw12 = vout12 * 2500 / 100  # kHz
ton24 = 100 / (24 * 2.5)  # us
ton20 = 100 / (20 * 2.5)
ton58 = 100 / (58.4 * 2.5)
rfbp = 91 * 10 / (91 + 10)  # kOhm
ca_min = 10 / (fsw12 * 1e3 * rfbp * 1e3) * 1e9  # nF
rc_lim20 = ton20 * 1e-6 * (20 - 12) / 0.02
rip24 = ton24 * 1e-6 * (24 - 12) / (75e3 * 10e-9) * 1e3
dI_58 = (58.4 - 12) * (12 / 58.4) / (47e-6 * fsw12 * 1e3)
block("02_AUX_12V", "AUX 12V BUCK",
      "LM5164 100 V COT buck VBUS -> 12 V / 0.5 A for the gate driver, comparators, fan and the 5 V buck; EN/UVLO divider keeps the aux rails off below ~16.5 V.",
      ["VBUS", "12V", "GND"],
      [part("U", "LM5164DDAR", "100 V 1 A COT buck", {1: "GND", 2: "VBUS", 3: "EN12", 4: "RON12", 5: "FB12", 7: "BST12", 8: "SW12", 9: "GND"}, nc=[6]),
       C(C1U100V, "1uF", "VBUS", "GND", "U VIN cap #1 at pin 2", "100V X7R 1206"),
       C(C1U100V, "1uF", "VBUS", "GND", "U VIN cap #2 at pin 2", "100V X7R 1206"),
       R(R110K, "110k", "VBUS", "EN12", "EN/UVLO divider top"),
       R(R10K, "10k", "EN12", "GND", "EN/UVLO divider bottom"),
       R(R100K, "100k", "RON12", "GND", "RON: sets fsw 300 kHz"),
       C(C2N2, "2.2nF", "BST12", "SW12", "BST cap 2.2 nF (datasheet-mandated 1.5-2.5 nF)", "50V X7R"),
       part("L", "SWPA6045S470MT", "12 V buck inductor 47 uH", {1: "SW12", 2: "12V"}, value="47uH", rating="Isat TO VERIFY >= 1.5 A"),
       R(R75K, "75k", "SW12", "RIP12", "Type-3 ripple injection RA (SW side)"),
       C(C10N, "10nF", "RIP12", "12V", "Type-3 ripple injection CA (across inductor with RA)", "50V X7R"),
       C(C100N, "100nF", "RIP12", "FB12", "Type-3 ripple injection CB (AC-couples ripple into FB)", "50V X7R"),
       R(R91K, "91k", "12V", "FB12", "FB divider top RFB1"),
       R(R10K, "10k", "FB12", "GND", "FB divider bottom RFB2"),
       C(C22U25, "22uF", "12V", "GND", "12 V output cap #1", "25V X5R 1206"),
       C(C22U25, "22uF", "12V", "GND", "12 V output cap #2", "25V X5R 1206"),
       R(R4K7, "4.7k", "12V", "LED12", "12 V power LED resistor"),
       part("D", "KT-0603G", "12V power LED (green)", {2: "LED12", 1: "GND"}, rating="Vf~2.0V")],
      [qa("Vout", "VOUT = VREF*(1+RFB1/RFB2), VREF 1.2 V (1.181-1.218)", f"{vout12:.2f} V (range {1.181*10.1:.2f}-{1.218*10.1:.2f} V)", "11.5-12.6 V; UCC21520 VDD 9.2-25 V", f"{DS} LM5164 s5.5 p5"),
       qa("fsw", "FSW(kHz) = VOUT*2500/RON(kOhm)", f"{fsw12:.0f} kHz", "<= 1000 kHz", f"{DS} LM5164 Eq.1 p10"),
       qa("tON range", "tON(us) = RON/(VIN*2.5)", f"{ton58*1e3:.0f} ns @58.4 V .. {ton20*1e3:.0f} ns @20 V", "tON >= 50 ns; tON>=300 ns so tOFF min 50 ns", f"{DS} LM5164 Eq.11 p12, s6.3.7 p13"),
       qa("Max duty / dropout at 20 V", "D = 12/20 = 0.6; tOFF = (1-D)/fsw", f"{(1-0.6)/fsw12*1e3:.0f} ns", ">= 50 ns min off", "calc"),
       qa("Type-3 CA", "CA >= 10/(FSW*(RFB1||RFB2))", f"CA >= {ca_min:.2f} nF -> 10 nF chosen (3.3 nF would FAIL)", "10 nF >= limit", f"{DS} LM5164 Eq.7 Table 6-1 p11 (|| assumed, check drawn eq.)"),
       qa("Type-3 RA*CA", "RA*CA <= tON*(VIN-VOUT)/20mV (evaluated at VIN_min 20 V, worst case)", f"75k*10nF = 7.5e-4 <= {rc_lim20:.2e}; FB ripple {rip24:.1f} mV @24 V", ">= 20 mV ripple", f"{DS} LM5164 Eq.8 p11"),
       qa("Type-3 CB", "CB >= t_settle/(3*RFB1) with t_settle 30 us", f">= {30e-6/(3*91e3)*1e12:.0f} pF -> 100 nF", "satisfied", f"{DS} LM5164 Eq.9 p11"),
       qa("EN/UVLO", "VIN_on = 1.5 V*(110k+10k)/10k; off = 1.4 V*12", f"on {1.5*12:.1f} V / off {1.4*12:.1f} V", "below 20 V min operating", f"{DS} LM5164 s5.5 p5"),
       qa("Inductor ripple", "dI = (VIN-VOUT)*D/(L*fsw) at 58.4 V", f"{dI_58:.2f} A pp; Ipk = 0.34+{dI_58/2:.2f} = {0.34+dI_58/2:.2f} A", "< 1.5 A peak current limit", "calc"),
       qa("Load", "sum of 12 V loads (REQUIREMENTS s3)", "0.343 A max", "<= 1 A rating (34 %)", "REQUIREMENTS.md s3"),
       qa("BST cap", "datasheet requirement", "2.2 nF 50 V X7R", "1.5-2.5 nF", f"{DS} LM5164 p3/p12"),
       qa("Cin voltage derating", "58.4/100", "58 %", "<= 80 %", "calc"),
       qa("Cout derating", "12/25", "48 % (X5R DC-bias derate to ~40 % C accepted; 2 caps)", "<= 80 % voltage", "calc"),
       qa("LED current", "(12-2.0)/4.7k", "2.1 mA", "<= 20 mA", "calc")])

# ---------------------------------------------------------------- 03 AUX 5 V / 3V3
vout5 = 0.596 * (1 + 75 / 10)
block("03_AUX_5V_3V3", "AUX 5V BUCK AND 3V3 LDO",
      "TPS54202 12 V -> 5 V buck, AP2112K 5 V -> 3.3 V LDO for MCU, CAN, current sense and logic.",
      ["12V", "5V", "3V3", "GND"],
      [part("U", "TPS54202DDCR", "28 V 2 A sync buck 12V->5V", {1: "GND", 2: "SW5", 3: "12V", 4: "FB5", 6: "BOOT5"}, nc=[5]),
       C(C10U25, "10uF", "12V", "GND", "U VIN bulk cap at pin 3", "25V X5R 0805"),
       C(C100N, "100nF", "12V", "GND", "U VIN HF cap at pin 3", "50V X7R"),
       C(C100N, "100nF", "BOOT5", "SW5", "BOOT cap 0.1 uF", "50V X7R"),
       part("L", "SWPA4030S100MT", "5 V buck inductor 10 uH", {1: "SW5", 2: "5V"}, value="10uH", rating="Isat TO VERIFY"),
       R(R75K, "75k", "5V", "FB5", "FB divider top"),
       R(R10K, "10k", "FB5", "GND", "FB divider bottom"),
       C(C22U25, "22uF", "5V", "GND", "5 V output cap #1", "25V X5R 1206"),
       C(C22U25, "22uF", "5V", "GND", "5 V output cap #2", "25V X5R 1206"),
       part("U", "AP2112K-3.3TRG1", "600 mA LDO 5V->3V3, EN tied high", {1: "5V", 2: "GND", 3: "5V", 5: "3V3"}, nc=[4]),
       C(C1U, "1uF", "5V", "GND", "LDO input cap at pin 1", "50V X5R"),
       C(C1U, "1uF", "3V3", "GND", "LDO output cap at pin 5", "50V X5R"),
       C(C4U7, "4.7uF", "3V3", "GND", "3V3 bulk", "16V X5R")],
      [qa("Vout 5V", "VOUT = 0.596*(1+75k/10k)", f"{vout5:.3f} V (range {0.581*8.5:.2f}-{0.611*8.5:.2f})", "4.8-5.2 V", f"{DS} TPS54202 s5.5 p5"),
       qa("VIN", "12 V input", "12.1 V", "4.5-28 V ROC", f"{DS} TPS54202 s5.3 p4"),
       qa("Inductor", "LMIN = (Vin-Vo)*Vo/(Vin*KIND*Io*fsw), Io design 0.3 A -> ripple ratio", f"dI = (12-5)*5/(12*10uH*500kHz) = {(7*5)/(12*10e-6*500e3):.2f} A pp; Ipk {0.15+0.29:.2f} A", "< 2 A rating; datasheet ref 15 uH is for 2 A load", f"{DS} TPS54202 s7.2.3 p15", True),
       qa("Cout", "2 x 22 uF 25 V as datasheet 5 V reference design", "2 x 22 uF 25 V", "matches reference", f"{DS} TPS54202 Fig7-1 p13"),
       qa("EN", "floating EN = enabled (internal pull-up), ABS 7 V so not tied to 12 V", "pin 5 NC", "documented", f"{DS} TPS54202 Table 4-1 p3"),
       qa("LDO dissipation", "(5-3.3)*0.122 A", f"{1.7*0.122:.2f} W -> Tj ~ 40+0.21*250 = 92 C", "< 125 C", "calc (thetaJA SOT-23-5 ~250 K/W ASSUMED, TO VERIFY)"),
       qa("3V3 load", "REQUIREMENTS s3", "0.122 A", "<= 0.6 A (20 %)", "REQUIREMENTS.md s3"),
       qa("5V load", "AP2112K input only (LM339 moved to 12 V)", "0.13 A", "<= 2 A", "calc")])

# ---------------------------------------------------------------- 04 MCU
mcu_pins = {1: "3V3", 5: "HSE_IN", 6: "HSE_OUT", 7: "NRST", 8: "ISENSE", 9: "VBUS_SNS", 10: "UART_TX", 11: "UART_RX",
            14: "FAULT_N", 15: "PWM_L", 16: "VOUT_SNS", 17: "NTC_SNS", 19: "GND", 20: "3V3", 21: "3V3", 23: "GND", 24: "3V3",
            30: "PWM_H", 33: "CAN_RX", 34: "CAN_TX", 35: "GND", 36: "3V3", 37: "SWDIO", 38: "SWCLK", 42: "LED_FLT",
            43: "FAN_PWM", 44: "DRV_DIS", 45: "BOOT0", 47: "GND", 48: "3V3"}
mcu_nc = [n for n in range(1, 49) if n not in mcu_pins]
block("04_MCU", "STM32G431 CONTROLLER",
      "STM32G431CBT6 (170 MHz, TIM1 complementary PWM + break input, ADC12, FDCAN1, USART2) with datasheet decoupling, 12 MHz HSE, SWD and UART headers, fault LED.",
      ["3V3", "GND", "ISENSE", "VBUS_SNS", "NTC_SNS", "VOUT_SNS", "FAULT_N", "PWM_H", "PWM_L", "DRV_DIS", "FAN_PWM", "CAN_TX", "CAN_RX"],
      [part("U", "STM32G431CBT6", "MCU: PA8 TIM1_CH1=PWM_H, PA7 TIM1_CH1N=PWM_L, PA6 TIM1_BKIN=FAULT_N, ADC PA0/PA1/PB0/PB1, FDCAN1 PA11/PA12, USART2 PA2/PA3", mcu_pins, nc=mcu_nc),
       C(C100N, "100nF", "3V3", "GND", "VDD pin 24 decoupling", "50V X7R"),
       C(C100N, "100nF", "3V3", "GND", "VDD pin 36 decoupling", "50V X7R"),
       C(C100N, "100nF", "3V3", "GND", "VDD pin 48 decoupling", "50V X7R"),
       C(C100N, "100nF", "3V3", "GND", "VBAT pin 1 decoupling", "50V X7R"),
       C(C4U7, "4.7uF", "3V3", "GND", "VDD bulk 4.7 uF", "16V X5R"),
       C(C10N, "10nF", "3V3", "GND", "VDDA pin 21 10 nF", "50V X7R"),
       C(C1U, "1uF", "3V3", "GND", "VDDA pin 21 1 uF", "50V X5R"),
       C(C100N, "100nF", "3V3", "GND", "VREF+ pin 20 100 nF", "50V X7R"),
       C(C1U, "1uF", "3V3", "GND", "VREF+ pin 20 1 uF", "50V X5R"),
       C(C100N, "100nF", "NRST", "GND", "NRST 0.1 uF at pin 7", "50V X7R"),
       R(R10K, "10k", "BOOT0", "GND", "BOOT0 pull-down: boot from flash"),
       part("Y", "X322512MSB4SI", "12 MHz HSE crystal 3225", {1: "HSE_IN", 3: "HSE_OUT", 2: "GND", 4: "GND"}, value="12MHz", rating="CL 20pF TO VERIFY"),
       C(C30P, "30pF", "HSE_IN", "GND", "HSE load cap OSC_IN", "50V C0G"),
       C(C30P, "30pF", "HSE_OUT", "GND", "HSE load cap OSC_OUT", "50V C0G"),
       part("J", "HDR-M_2.54_1x5P", "SWD header: 1 3V3, 2 SWCLK, 3 GND, 4 SWDIO, 5 NRST", {1: "3V3", 2: "SWCLK", 3: "GND", 4: "SWDIO", 5: "NRST"}),
       part("J", "HDR-M_2.54_1x3P", "UART header: 1 TX (MCU out), 2 RX (MCU in), 3 GND", {1: "UART_TX", 2: "UART_RX", 3: "GND"}),
       R(R1K, "1k", "LED_FLT", "LEDF_A", "fault LED resistor"),
       part("D", "KT-0603R", "FAULT LED (red), driven by PB5", {1: "LEDF_A", 2: "GND"}, rating="Vf~2.0V")],
      [qa("Decoupling", "per DS12589 Fig 16: VDD n x 100 nF + 4.7 uF; VDDA 10 nF + 1 uF; VREF+ 100 nF + 1 uF", "3 x 100 nF VDD + 100 nF VBAT + 4.7 uF; VDDA 10 nF + 1 uF; VREF+ 100 nF + 1 uF", "matches", f"{DS} STM32 s5.1.6 p68"),
       qa("VREF+", "VREF+ = VDDA (tied to 3V3); VDDA >= 2 V", "3.3 V", "2 V..VDDA", f"{DS} STM32 s3.11.1 p22"),
       qa("Alternate functions", "Table 13", "PA8 AF6 TIM1_CH1, PA7 AF6 TIM1_CH1N, PA6 AF6 TIM1_BKIN, PA11/PA12 AF9 FDCAN1, PA2/PA3 AF7 USART2, PA13/PA14 SWD", "no conflicts (PA14 kept as SWCLK only)", f"{DS} STM32 Table 13 p61-62"),
       qa("ADC inputs", "Table 12", "PA0 ADC12_IN1 ISENSE, PA1 ADC12_IN2 VBUS_SNS, PB0 ADC1_IN15 VOUT_SNS, PB1 ADC1_IN12 NTC_SNS", "all ADC capable", f"{DS} STM32 Table 12 p51-53"),
       qa("NRST", "0.1 uF to GND", "100 nF", "matches", f"{DS} STM32 Fig 27 p121"),
       qa("BOOT0", "PB8-BOOT0 low = boot from flash (nBOOT_SEL default)", "10k pull-down", "flash boot", f"{DS} STM32 s3.5 p19"),
       qa("HSE load caps", "C = 2*(CL - Cstray), CL 20 pF (part code S, TO VERIFY), Cstray 5 pF", "30 pF", "crystal datasheet TO VERIFY", "calc"),
       qa("Fault LED", "(3.3-2.0)/1k", "1.3 mA", "<= 20 mA GPIO", "calc")])

# ---------------------------------------------------------------- 05 CAN
block("05_CAN", "CAN TRANSCEIVER",
      "SN65HVD230 3.3 V CAN transceiver (high-speed mode, RS to GND), fixed 120 Ohm termination, CAN ESD array, 3-pin header. RS485 not populated on rev A.",
      ["3V3", "GND", "CAN_TX", "CAN_RX"],
      [part("U", "SN65HVD230DR", "3.3 V CAN transceiver", {1: "CAN_TX", 2: "GND", 3: "3V3", 4: "CAN_RX", 6: "CANL", 7: "CANH", 8: "GND"}, nc=[5]),
       C(C100N, "100nF", "3V3", "GND", "U VCC decoupling at pin 3", "50V X7R"),
       R(R120, "120", "CANH", "CANL", "bus termination 120 Ohm (fixed; board is a bus end)"),
       part("D", "NUP2105LT1G", "CAN bus ESD protection (pins 1/2 CANH/CANL, 3 GND)", {1: "CANH", 2: "CANL", 3: "GND"}),
       part("J", "HDR-M_2.54_1x3P", "CAN header: 1 CANH, 2 CANL, 3 GND", {1: "CANH", 2: "CANL", 3: "GND"})],
      [qa("Supply", "3.0-3.6 V", "3.3 V", "in range", f"{DS} SN65HVD230 s8.3 p6"),
       qa("RS mode", "RS strong pull-down = high speed", "RS = GND", "1 Mb/s capable", f"{DS} SN65HVD230 p5"),
       qa("Termination", "Z0 120 Ohm bus end", "120 Ohm 0603", "P = (2V)^2/120 = 33 mW <= 100 mW", "calc")])

# ---------------------------------------------------------------- 06 GATE DRIVER
block("06_GATE_DRV", "ISOLATED GATE DRIVER",
      "UCC21520 dual isolated gate driver (8 V UVLO) for the half-bridge with bootstrap high side, 200 ns hardware dead time, default-disabled DIS, and 74LVC2G08 AND gating of both PWM inputs with FAULT_N (hardware shutdown independent of firmware).",
      ["3V3", "12V", "GND", "PWM_H", "PWM_L", "FAULT_N", "DRV_DIS", "GH", "GL", "SW", "INA_S", "INB_S"],
      [part("U", "SN74LVC2G08DCUR", "dual AND: INA_S = PWM_H & FAULT_N, INB_S = PWM_L & FAULT_N", {1: "PWM_H", 2: "FAULT_N", 7: "INA_S", 5: "PWM_L", 6: "FAULT_N", 3: "INB_S", 4: "GND", 8: "3V3"}),
       C(C100N, "100nF", "3V3", "GND", "AND gate VCC decoupling", "50V X7R"),
       R(R10K, "10k", "PWM_H", "GND", "PWM_H pull-down (gate off while MCU in reset)"),
       R(R10K, "10k", "PWM_L", "GND", "PWM_L pull-down (gate off while MCU in reset)"),
       part("U", "UCC21520DWR", "isolated dual gate driver; A = high side (VSSA=SW), B = low side (VSSB=GND)",
            {1: "INA_S", 2: "INB_S", 3: "3V3", 4: "GND", 5: "DRV_DIS", 6: "DT", 8: "3V3", 9: "GND", 10: "GLO", 11: "12V", 14: "SW", 15: "GHO", 16: "BST"}, nc=[7, 12, 13]),
       C(C100N, "100nF", "3V3", "GND", "VCCI 100 nF at pin 3/8", "50V X7R"),
       C(C1U, "1uF", "3V3", "GND", "VCCI bulk 1 uF", "50V X5R"),
       R(R10K, "10k", "DRV_DIS", "3V3", "DIS pull-up: driver DISABLED at reset (MCU drives low to enable)"),
       C(C1N, "1nF", "DRV_DIS", "GND", "DIS pin 1 nF bypass", "50V X7R"),
       R(R20K, "20k", "DT", "GND", "dead-time resistor 20k -> 200 ns"),
       C(C1N, "1nF", "DT", "GND", "1 nF parallel with RDT (RDT > 5k)", "50V X7R"),
       C(C10U25, "10uF", "12V", "GND", "VDDB 10 uF at pin 11", "25V X5R 0805"),
       C(C100N, "100nF", "12V", "GND", "VDDB 100 nF at pin 11", "50V X7R"),
       R(R10, "10", "12V", "BSTR", "bootstrap series resistor"),
       part("D", "STPS1H100A", "bootstrap diode 100 V Schottky (A = BSTR, K = BST)", {2: "BSTR", 1: "BST"}, rating="100V 1A"),
       C(C1U, "1uF", "BST", "SW", "bootstrap cap 1 uF (VDDA-VSSA)", "50V X5R"),
       C(C100N, "100nF", "BST", "SW", "bootstrap HF cap 100 nF", "50V X7R"),
       R(R10, "10", "GHO", "GH", "high-side gate resistor"),
       R(R10, "10", "GLO", "GL", "low-side gate resistor"),
       R(R10K, "10k", "GH", "SW", "high-side gate-source pull-down"),
       R(R10K, "10k", "GL", "GND", "low-side gate-source pull-down")],
      [qa("VDD vs UVLO", "UCC21520 (8 V UVLO): VDD ROC 9.2-25 V, UVLO rise 8.5 V typ", "VDDB 12.1 V; VDDA = 12.1 - VF(0.77) - I*R ~ 11.2 V", "> 9.2 V ROC", f"{DS} UCC21520 s6.3 p5 / s6.8 p8"),
       qa("Dead time", "tDT(ns) = 10*RDT(kOhm)", "20k -> 200 ns (160-240); +1 nF parallel", "RDT 2-500k", f"{DS} UCC21520 s8.4.2.2 p23"),
       qa("DIS default", "DIS active high, internal pull-down; external 10k pull-up to VCCI", "outputs disabled at reset / MCU in reset", "fail-safe", f"{DS} UCC21520 Table 5-1 p4, s8.4.1 p23"),
       qa("Bootstrap cap", "C >= 10 x Qg/dV; Qg 55 nC max, dV 0.5 V", "1.1 uF -> 1 uF + 100 nF (TI example 1 uF + 100 nF)", "accepted", f"{DS} BSC070N10NS3 Table 6 p4; UCC21520 s9.2.2.7.2 p32"),
       qa("Bootstrap diode", "VRRM >= VBUS max + VDD", "100 V >= 58.4+12 = 70.4 V (70 %)", "<= 80 %", f"{DS} STPS1H100 Table 2 p2 (automotive -Y datasheet variant, commercial A TO VERIFY)"),
       qa("Gate drive current", "Ipk = VDD/(Rg + Rdrv) ~ 12/10", "1.2 A peak", "<= 4 A source / 6 A sink", f"{DS} UCC21520 s6.9 p9"),
       qa("Gate charge power", "P = Qg*VDD*f per FET = 55n*12*20k", f"{55e-9*12*20e3*1e3:.1f} mW per channel", "negligible", "calc"),
       qa("Isolation", "UCC21520 DW: VIOTM 8000 Vpk, CPG/CLR > 8 mm", "functional only on rev A: GND on both sides (single reference, SELV). Barrier preserved in copper by keep-out.", "NO safety isolation claimed", f"{DS} UCC21520 s6.6 p7"),
       qa("AND gate", "74LVC2G08: INA_S = PWM_H AND FAULT_N", "FAULT_N low forces both driver inputs low within gate tpd (ns), independent of firmware", "hardware shutdown", "logic")])

# ---------------------------------------------------------------- 07 HALF BRIDGE
rs = 0.005
i_fs = (3.3 - 0.05 - 1.65) / (20 * rs)
pcond = 25 * 0.007 * 1.5 * 0.5
psw = 0.5 * 58.4 * 10 * 40e-9 * 20e3
block("07_HALF_BRIDGE", "HALF BRIDGE POWER STAGE",
      "100 V MOSFET half-bridge on VBUS with local MLCC hot-loop decoupling, 5 mOhm phase shunt with INA240A1 bidirectional sense, NTC on the low-side FET, and the 4-way output terminal (PHASE, VBUS, GND, VOUT_EXT sense) for an external LC filter / load.",
      ["VBUS", "GND", "3V3", "GH", "GL", "SW", "ISENSE", "NTC_SNS", "VOUT_SNS"],
      [part("Q", "BSC070N10NS3G", "high-side MOSFET (D=VBUS, S=SW)", {1: "SW", 2: "SW", 3: "SW", 4: "GH", 5: "VBUS", 6: "VBUS", 7: "VBUS", 8: "VBUS"}, rating="100V 7mOhm"),
       part("Q", "BSC070N10NS3G", "low-side MOSFET (D=SW, S=GND)", {1: "GND", 2: "GND", 3: "GND", 4: "GL", 5: "SW", 6: "SW", 7: "SW", 8: "SW"}, rating="100V 7mOhm"),
       C(C2U2_100V, "2.2uF", "VBUS", "GND", "hot-loop MLCC #1 across Q1 drain / Q2 source", "100V X7R 1210"),
       C(C2U2_100V, "2.2uF", "VBUS", "GND", "hot-loop MLCC #2", "100V X7R 1210"),
       C(C2U2_100V, "2.2uF", "VBUS", "GND", "hot-loop MLCC #3", "100V X7R 1210"),
       C(C100N100V, "100nF", "VBUS", "GND", "hot-loop HF MLCC closest to the FETs", "100V X7R 0603"),
       part("R", "PA2512FKF7W0R005E", "phase current shunt 5 mOhm 2512 (Kelvin-sensed by U IN+/IN-)", {1: "SW", 2: "PHASE"}, value="5mR", rating="2W 1%"),
       part("U", "INA240A1PWR", "bidirectional PWM-rejecting current sense amp, gain 20, OUT = VS/2 at 0 A", {2: "SW", 3: "PHASE", 4: "GND", 5: "3V3", 6: "GND", 7: "3V3", 8: "ISENSE_RAW"}, nc=[1]),
       C(C100N, "100nF", "3V3", "GND", "INA240 VS decoupling", "50V X7R"),
       R(R1K, "1k", "ISENSE_RAW", "ISENSE", "INA240 output RC filter R (TI recommends output filtering)"),
       C(C1N, "1nF", "ISENSE", "GND", "INA240 output RC filter C (tau 1 us, comparator blanking)", "50V X7R"),
       part("RT", "NCP18XH103F03RB", "NTC 10k B3380 at low-side FET", {1: "NTC_SNS", 2: "GND"}, value="10k NTC"),
       R(R10K, "10k", "3V3", "NTC_SNS", "NTC pull-up"),
       C(C100N, "100nF", "NTC_SNS", "GND", "NTC filter cap", "50V X7R"),
       part("J", "WJ128V-5.0-04P-14-00A", "output terminal: 1 PHASE, 2 VBUS, 3 GND, 4 VOUT_EXT (filtered output sense)", {1: "PHASE", 2: "VBUS", 3: "GND", 4: "VOUT_EXT"}),
       R(R100K, "100k", "VOUT_EXT", "VOUT_SNS", "VOUT sense divider top"),
       R(R5K1, "5.1k", "VOUT_SNS", "GND", "VOUT sense divider bottom"),
       C(C100N, "100nF", "VOUT_SNS", "GND", "VOUT_SNS filter cap", "50V X7R")],
      [qa("FET voltage derating", "VBUS_max/VDS", "58.4/100 = 58 %", "<= 80 %", f"{DS} BSC070N10NS3 Table 1"),
       qa("FET current", "ID(TC 100C) vs Ipk", "58 A vs 10 A", "ok", f"{DS} BSC070N10NS3 Table 2"),
       qa("FET loss (each)", "Pcond = I^2*Rds*1.5*D, Psw = 0.5*V*Ipk*(tr+tf)*f, tr+tf 40 ns ASSUMED (gate R 10 Ohm, Qg 42 nC)", f"Pcond {pcond:.3f} W + Psw {psw:.3f} W = {pcond+psw:.2f} W", "-", f"{DS} BSC070N10NS3 Table 4/6; calc"),
       qa("FET Tj", "Tj = Ta + P*RthJA, Ta 40 C, RthJA 50 K/W (6 cm2 Cu)", f"{40+(pcond+psw)*50:.0f} C", "< 150 C (THERM-TJ-050 UNSUPPORTED in DESK: hand calc)", f"{DS} BSC070N10NS3 Table 3"),
       qa("Shunt power", "I^2*R at 5 A RMS", f"{25*rs:.3f} W (10 A pk {100*rs:.2f} W)", "<= 2 W (6 %)", "calc"),
       qa("ISENSE scale", "OUT = 1.65 + 20*0.005*I", "1.65 V +/- 0.1 V/A; +/-10 A -> 0.65..2.65 V", f"full scale +/-{i_fs:.1f} A before output swing limit", f"{DS} INA240 s8.4.3.2 p14, s7.5"),
       qa("INA240 CM range", "-4..80 V", "PHASE 0..58.4 V (73 %)", "in range", f"{DS} INA240 s7.3 p4"),
       qa("INA240 input filter", "not required / not recommended", "none fitted", "per datasheet", f"{DS} INA240 s9.1.1 p18"),
       qa("Hot-loop MLCC derating", "58.4/100", "58 %; X7R DC-bias C loss accepted, 3 x 2.2 uF + 100 nF", "<= 80 %", "calc"),
       qa("Output filter (external)", "L >= VBUS/(4*dI*f) for dI 30 % of 5 A at 24 V", f"L >= {24/(4*1.5*20e3)*1e6:.0f} uH (at 58.4 V: {58.4/(4*1.5*20e3)*1e6:.0f} uH) -> off-board lab inductor via J", "documented", "calc"),
       qa("VOUT_SNS scale", "same 100k/5.1k divider", f"60 V -> {60*vs_ratio:.2f} V", "< 3.3 V", "calc"),
       qa("Terminal rating", "WJ128V-5.0 current rating", "TO VERIFY from LCSC datasheet (typ 15-16 A class for 5.0 mm)", ">= 10 A", "TO VERIFY", True)])

# ---------------------------------------------------------------- 08 PROTECTION
def div(top, bot):
    return 3.3 * bot / (top + bot)


v_ocp, v_ocn, v_ot, v_ov = div(10, 40.2), div(40.2, 10), div(100, 10), div(10, 75)
r_ntc = 10 * v_ot / (3.3 - v_ot)
t_ot = 1 / (1 / 298.15 + math.log(r_ntc / 10) / 3380) - 273.15
block("08_PROTECTION", "HARDWARE PROTECTION COMPARATORS",
      "LM339 quad comparator (12 V supply, open-collector wired-OR to FAULT_N): overcurrent both directions, over-temperature (NTC) and VBUS overvoltage. FAULT_N gates the driver inputs (block 06) and drives TIM1_BKIN.",
      ["12V", "3V3", "GND", "ISENSE", "NTC_SNS", "VBUS_SNS", "FAULT_N"],
      [part("U", "LM339DR", "quad comparator: C1 OC+, C2 OC-, C3 OT, C4 OV; outputs wired-OR FAULT_N",
            {1: "FAULT_N", 2: "FAULT_N", 3: "12V", 4: "REF_OCN", 5: "ISENSE", 6: "ISENSE", 7: "REF_OCP", 8: "REF_OT", 9: "NTC_SNS",
             10: "VBUS_SNS", 11: "REF_OV", 12: "GND", 13: "FAULT_N", 14: "FAULT_N"}),
       C(C100N, "100nF", "12V", "GND", "LM339 VCC decoupling at pin 3", "50V X7R"),
       R(R10K, "10k", "3V3", "REF_OCP", "OC+ reference top"),
       R(R40K2, "40.2k", "REF_OCP", "GND", "OC+ reference bottom"),
       C(C100N, "100nF", "REF_OCP", "GND", "OC+ reference filter", "50V X7R"),
       R(R40K2, "40.2k", "3V3", "REF_OCN", "OC- reference top"),
       R(R10K, "10k", "REF_OCN", "GND", "OC- reference bottom"),
       C(C100N, "100nF", "REF_OCN", "GND", "OC- reference filter", "50V X7R"),
       R(R100K, "100k", "3V3", "REF_OT", "OT reference top"),
       R(R10K, "10k", "REF_OT", "GND", "OT reference bottom"),
       C(C100N, "100nF", "REF_OT", "GND", "OT reference filter", "50V X7R"),
       R(R10K, "10k", "3V3", "REF_OV", "OV reference top"),
       R(R75K, "75k", "REF_OV", "GND", "OV reference bottom"),
       C(C100N, "100nF", "REF_OV", "GND", "OV reference filter", "50V X7R"),
       R(R4K7, "4.7k", "FAULT_N", "3V3", "FAULT_N pull-up (open-collector wired-OR)")],
      [qa("OC+ trip", "ISENSE > REF_OCP: Itrip = (Vref-1.65)/(20*5mOhm)", f"REF {v_ocp:.3f} V -> +{(v_ocp-1.65)/0.1:.2f} A", "~10 A", "calc (ratiometric to 3V3, same as INA240 REF)"),
       qa("OC- trip", "ISENSE < REF_OCN", f"REF {v_ocn:.3f} V -> -{(1.65-v_ocn)/0.1:.2f} A", "~10 A", "calc"),
       qa("OT trip", "NTC_SNS < REF_OT; R_ntc = 10k*V/(3.3-V); T = 1/(1/298.15 + ln(R/10k)/B), B25/50 = 3380 K (Murata NCP18XH series code XH; datasheet TO VERIFY)", f"REF {v_ot:.3f} V -> R_ntc {r_ntc:.3f} k -> {t_ot:.1f} C (B=3380)", "~100 C board/FET-case trip", "calc", True),
       qa("OV trip", "VBUS_SNS > REF_OV: VBUS = Vref/0.04852", f"REF {v_ov:.3f} V -> {v_ov/vs_ratio:.1f} V", "> 58.4 V max operating, < 96.8 V clamp", "calc"),
       qa("LM339 CM range at 12 V", "0..VCC-2 V over temp = 0..10 V", "all inputs <= 3.3 V", "in range", f"{DS} LM339 s6.10 p10"),
       qa("Output", "open collector, wired-OR, 4.7k pull-up to 3V3", "0.7 mA sink when low", "<= 6 mA min sink", f"{DS} LM339 s7.1 p19"),
       qa("Response", "INA240 + 1 us RC + LM339 (~1 us) + AND gate", "~2-3 us to gate-off (estimate, to be MEASURED at bring-up)", "cycle-by-cycle; TIM1 BKIN latches", "calc", True),
       qa("Hysteresis", "none (wired-OR)", "cycle-by-cycle limiting; latch is TIM1 BKIN in MCU", "documented limitation", "design")])

# ---------------------------------------------------------------- 09 FAN + INSTRUMENT
block("09_FAN_IO", "FAN DRIVE AND INSTRUMENT HEADER",
      "Low-side 12 V fan switch with flyback diode, and an 8-pin oscilloscope / instrument header carrying gated PWM, FAULT_N and all analog sense nodes.",
      ["12V", "GND", "FAN_PWM", "INA_S", "INB_S", "FAULT_N", "ISENSE", "VBUS_SNS", "NTC_SNS", "VOUT_SNS"],
      [part("J", "HDR-M_2.54_1x2P", "fan header: 1 +12V, 2 FAN- (switched)", {1: "12V", 2: "FAN_N"}),
       part("Q", "AO3400A", "fan low-side switch N-MOSFET", {1: "FAN_G", 2: "GND", 3: "FAN_N"}, rating="30V 5.7A"),
       part("D", "1N4148W", "fan flyback diode (K = 12V, A = FAN_N)", {1: "12V", 2: "FAN_N"}),
       R(R100, "100", "FAN_PWM", "FAN_G", "fan MOSFET gate resistor"),
       R(R100K, "100k", "FAN_G", "GND", "fan MOSFET gate pull-down (off at reset)"),
       part("J", "HDR-M_2.54_1x8P", "instrument header: 1 GND 2 INA_S 3 INB_S 4 FAULT_N 5 ISENSE 6 VBUS_SNS 7 NTC_SNS 8 VOUT_SNS",
            {1: "GND", 2: "INA_S", 3: "INB_S", 4: "FAULT_N", 5: "ISENSE", 6: "VBUS_SNS", 7: "NTC_SNS", 8: "VOUT_SNS"})],
      [qa("Fan switch", "AO3400A Vgs(th) vs 3.3 V drive, Id vs 0.25 A", "3.3 V gate drive adequate for 0.25 A (Rds(on)@2.5V ~ 50 mOhm class, TO VERIFY)", ">= 0.25 A", "AO3400A datasheet TO VERIFY", True),
       qa("Flyback", "1N4148W 75 V / 150 mA cont, fan current 0.25 A transient only", "decay current < 0.25 A for us", "IFSM >> transient", "TO VERIFY", True)])

os.makedirs(OUT, exist_ok=True)
for b in blocks:
    with open(os.path.join(OUT, b["id"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1)
print(len(blocks), "blocks,", sum(len(b["parts"]) for b in blocks), "parts")
