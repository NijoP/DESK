# Run 2, attempt 1: ABORTED (not graded as a completed run)

- Clock: 12:12:46 to 13:53:38 (100.87 min elapsed; Stage 1 never closed).
- Stage 1 work done: 4 blocks built and VERIFIED (40 parts, 43 nets); C9/C10 added on 5V; 2x2 relayout; ERC 0 errors / 2 warnings, with the itemized audit in schematic_reports/erc_report.txt.
- Abort cause (H-R2-001): the builder asked the Captain to delete 7 API-invisible ghost texts. The Captain deleted the
  entire schematic and PCB in the GUI instead and ordered "start from beginning". Designated window 3287eb7d then
  disconnected. The builder waited about 89 minutes until the Captain designated window dd882e4f (same project and document uuids).
- Captain decision (AskUserQuestion, 13:53): "Restart as run 2b". Fresh 225-min clock, same rules, budgets and examiner.
- Everything here is preserved unchanged. Failure entries R2-F-001..003 carry into run 2b's register as known lessons.
