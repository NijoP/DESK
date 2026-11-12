# T+70 Report (T+70 = 06:00:28)
**LATE and RETROACTIVE.** Written ~06:10 (about T+79.5) from files/logs/CSV; not live.

## State at T+70 (reconstructed)
- Stage 3 elapsed ~29.5 min. run2 (6.5 mil + GND routed) was killed with 7 unrouted, no SES (fr.log last write 05:59:27). run3 (5 mil + GND) started 05:59:51, finished 06:02:54 with 9 unrouted (SES written but incomplete). run4 (GND removed from router, 5 mil) 06:03:38: 66 clearance errors plus USB opens (drc_raw_run4 06:03:51, 148 KB). run5 (6.1 mil, no GND) 06:04:33: USB_DP/DN open because the ESD part was too close (drc_raw_run5 06:04:44).
- Interpretation: the builder iterated on router parameters, then dropped GND from the router (deliberate engineering choice, assessed in the T+80 report) after GND routing failed to complete on 2 layers. Run history is documented in ROUTING_RECORD.md and agrees with the file times.
- Failures F-013 (probe timeout of Freerouting 2.1.0 --help), F-014 (2.1.0 writes no SES when supervisor stops it; -mp ignored, 819 passes at -mp 40) are labelled CONFIRMED and have measurement-backed explanations; I did not reproduce them but the fr.log files and the ~10 min run2 duration are consistent. Cost: F-014 about 12 min lost.
## Hardware 05:50-05:59 (CSV)
- CPU 67-81 %; java 13-14 % CPU, WS 1.16-1.23 GB (steady, no leak); EasyEDA 39-42 %, WS 1.55-2.2 GB; Claude WS fell to 1.27 GB at 05:58:51 (1.46 earlier). RAM available 872 MB min (05:57:50), mostly 1.5-2 GB. Net bursts to 2.8 MB/s at 05:51:48 (unexplained). GPU idle 0 %/46-48 C.
