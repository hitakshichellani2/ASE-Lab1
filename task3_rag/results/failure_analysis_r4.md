# Failure analysis (r4)

13 of 50 judged answers are not fully correct (12 retrieval failures, 1 generation failures).

Pick 5 for the report/video, ideally from different categories, and write down WHY for each.

## dev079  [identifier]  -> GENERATION failure

- **Question:** What is the recommended fix for PQ-E1799?
- **Ground truth:** Throttling protects the node. Add capacity or reduce load. As a last resort, raise `retention.threshold_percent`.
- **System answer:** In PaderQueue 4.x, add capacity or reduce load; as a last resort, raise `retention.threshold_percent`.
- **Judge:** correctness 0.5 - It gives the recommended actions but omits that throttling protects the node.
- **Needed documents:** (d0649)
- **Given to the generator (rank order):** d0712 (forum: PQ-E1799 after upgrade?), d0649 (error: PQ-E1799 RETENTION_THROTTLED), d0589 (forum: Getting 'retention: throttled' all the time), d0336 (forum: Getting 'retention: throttled' all the time), d0019 (forum: Getting 'retention: throttled' all the time)
- **Missing pieces:** none
- **Classification:** all needed documents were in the context, but the answer is wrong
- **Your explanation (why did it fail?):** 

## dev025  [multi-hop]  -> RETRIEVAL failure

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2024-171?
- **Ground truth:** The incident was caused by PQ-E1915. Fix: Throttling protects the node. Add capacity or reduce load. As a last resort, raise `metrics.threshold_percent`.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The documentation provides a fix for PQ-E1915: add capacity or reduce load, and raise `metrics.threshold_percent` only as a last resort.
- **Needed documents:** (d0253) AND (d0183)
- **Given to the generator (rank order):** d0253 (incident: Postmortem INC-2024-171), d0804 (incident: Postmortem INC-2024-214), d0215 (incident: Postmortem INC-2024-177), d0641 (incident: Postmortem INC-2024-170), d0914 (incident: Postmortem INC-2024-106)
- **Missing pieces:** [['d0183']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev030  [multi-hop]  -> RETRIEVAL failure

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2025-175?
- **Ground truth:** The incident was caused by PQ-E2617. Fix: Check the logs for the underlying failure first. If the failures are transient, increase `dlq.max_retries`.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The documentation does contain the recommended fix: check logs for the underlying failure, and if failures are transient, increase `dlq.max_retries`.
- **Needed documents:** (d0442) AND (d0174)
- **Given to the generator (rank order):** d0442 (incident: Postmortem INC-2025-175), d0496 (incident: Postmortem INC-2025-142), d0790 (incident: Postmortem INC-2025-127), d0535 (incident: Postmortem INC-2025-220), d0118 (incident: Postmortem INC-2025-193)
- **Missing pieces:** [['d0174']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev032  [multi-hop]  -> RETRIEVAL failure

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2024-213?
- **Ground truth:** The incident was caused by PQ-E3891. Fix: Add worker threads or increase `compactor.queue_capacity`. A queue that stays full usually means the component is too slow.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The documentation identifies PQ-E3891 and recommends adding worker threads or increasing `compactor.queue_capacity`, noting that a persistently full queue usually means the component is too slow.
- **Needed documents:** (d0377) AND (d0350)
- **Given to the generator (rank order):** d0377 (incident: Postmortem INC-2024-213), d0804 (incident: Postmortem INC-2024-214), d0253 (incident: Postmortem INC-2024-171), d0077 (incident: Postmortem INC-2024-120), d0801 (incident: Postmortem INC-2024-210)
- **Missing pieces:** [['d0350']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev042  [multi-hop]  -> RETRIEVAL failure

- **Question:** What is the current default value of the setting that the error catalogue recommends changing for PQ-E2051?
- **Ground truth:** `compactor.compression` defaults to `lz4` in 4.x.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The answer says the information is unavailable, but the default is `lz4` for `compactor.compression` in 4.x.
- **Needed documents:** (d0738) AND (d0564)
- **Given to the generator (rank order):** d0785 (forum: PQ-E2051 after upgrade?), d0770 (forum: Getting 'compactor: codec mismatch' all the time), d0324 (incident: Postmortem INC-2025-169), d0192 (changelog: PaderQueue 2.0 release notes), d0738 (error: PQ-E2051 COMPACTOR_CODEC_MISMATCH)
- **Missing pieces:** [['d0564']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev047  [multi-hop]  -> RETRIEVAL failure

- **Question:** What is the current default value of the setting that the error catalogue recommends changing for PQ-E2425?
- **Ground truth:** `acktracker.max_retries` defaults to `20` in 4.x.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - It says the documentation lacks the information, but the setting `acktracker.max_retries` defaults to `20` in 4.x.
- **Needed documents:** (d0522) AND (d0749)
- **Given to the generator (rank order):** d0576 (forum: PQ-E2425 after upgrade?), d0517 (forum: PQ-E2425 after upgrade?), d0522 (error: PQ-E2425 ACKTRACKER_RETRIES_EXHAUSTED), d0055 (forum: PQ-E2622 after upgrade?), d0116 (forum: Getting 'acktracker: retries exhausted' all the time)
- **Missing pieces:** [['d0749']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev065  [multi-hop]  -> RETRIEVAL failure

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2025-101?
- **Ground truth:** The incident was caused by PQ-E3177. Fix: Check for connection leaks in clients (connections that are never closed). If the load is legitimate, increase `scheduler.max_connections`.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The documentation contains the fix: check for client connection leaks, and if the load is legitimate, increase `scheduler.max_connections`.
- **Needed documents:** (d0919) AND (d0227)
- **Given to the generator (rank order):** d0919 (incident: Postmortem INC-2025-101), d0496 (incident: Postmortem INC-2025-142), d0790 (incident: Postmortem INC-2025-127), d0313 (incident: Postmortem INC-2025-114), d0535 (incident: Postmortem INC-2025-220)
- **Missing pieces:** [['d0227']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev069  [multi-hop]  -> RETRIEVAL failure

- **Question:** What is the current default value of the setting that the error catalogue recommends changing for PQ-E4020?
- **Ground truth:** `spool.compression` defaults to `lz4` in 4.x.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - It says the information is unavailable, but the default is `lz4` in 4.x.
- **Needed documents:** (d0506) AND (d0679)
- **Given to the generator (rank order):** d0237 (forum: PQ-E4020 after upgrade?), d0510 (forum: PQ-E4020 after upgrade?), d0506 (error: PQ-E4020 SPOOL_CODEC_MISMATCH), d0769 (forum: Help: spool: codec mismatch in production), d0055 (forum: PQ-E2622 after upgrade?)
- **Missing pieces:** [['d0679']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev083  [multi-hop]  -> RETRIEVAL failure

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2024-147?
- **Ground truth:** The incident was caused by PQ-E2051. Fix: Set `compactor.compression` to the same value on all nodes, then restart them one after another.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The documentation recommends setting `compactor.compression` to the same value on all nodes and restarting them one after another.
- **Needed documents:** (d0786) AND (d0738)
- **Given to the generator (rank order):** d0786 (incident: Postmortem INC-2024-147), d0804 (incident: Postmortem INC-2024-214), d0215 (incident: Postmortem INC-2024-177), d0914 (incident: Postmortem INC-2024-106), d0641 (incident: Postmortem INC-2024-170)
- **Missing pieces:** [['d0738']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev089  [multi-hop]  -> RETRIEVAL failure

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2024-166?
- **Ground truth:** The incident was caused by PQ-E4013. Fix: Throttling protects the node. Add capacity or reduce load. As a last resort, raise `auth.threshold_percent`.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The documentation provides a fix for PQ-E4013: add capacity or reduce load, and only as a last resort raise `auth.threshold_percent`.
- **Needed documents:** (d0602) AND (d0229)
- **Given to the generator (rank order):** d0602 (incident: Postmortem INC-2024-166), d0135 (incident: Postmortem INC-2024-186), d0914 (incident: Postmortem INC-2024-106), d0804 (incident: Postmortem INC-2024-214), d0378 (incident: Postmortem INC-2024-164)
- **Missing pieces:** [['d0229']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev119  [multi-hop]  -> RETRIEVAL failure

- **Question:** What is the current default value of the setting that the error catalogue recommends changing for PQ-E1799?
- **Ground truth:** `retention.threshold_percent` defaults to `95` in 4.x.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The answer says the information is unavailable, but the default is `95` in 4.x.
- **Needed documents:** (d0649) AND (d0365)
- **Given to the generator (rank order):** d0712 (forum: PQ-E1799 after upgrade?), d0649 (error: PQ-E1799 RETENTION_THROTTLED), d0589 (forum: Getting 'retention: throttled' all the time), d0336 (forum: Getting 'retention: throttled' all the time), d0019 (forum: Getting 'retention: throttled' all the time)
- **Missing pieces:** [['d0365']]
- **Classification:** 1 of 2 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev004  [paraphrase]  -> RETRIEVAL failure

- **Question:** Which setting controls how many times the mechanism that parks messages nobody could process tries again before it gives up?
- **Ground truth:** The setting `dlq.max_retries`.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - The answer says the information is unavailable, but the setting is `dlq.max_retries`.
- **Needed documents:** (d0032 or d0303)
- **Given to the generator (rank order):** d0805 (changelog: PaderQueue 2.1 release notes), d0749 (config: acktracker.max_retries), d0806 (error: PQ-E2995 QUOTA_RETRIES_EXHAUSTED), d0655 (config: spool.max_retries), d0735 (config: acktracker.timeout_ms)
- **Missing pieces:** [['d0032', 'd0303']]
- **Classification:** 1 of 1 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 

## dev087  [paraphrase]  -> RETRIEVAL failure

- **Question:** Which setting limits how many clients can talk to the part that holds back messages until a later point in time in parallel?
- **Ground truth:** The setting `scheduler.max_connections`.
- **System answer:** The documentation does not contain this information.
- **Judge:** correctness 0.0 - It says the information is unavailable, but the setting is `scheduler.max_connections`.
- **Needed documents:** (d0153)
- **Given to the generator (rank order):** d0870 (changelog: PaderQueue 1.2 release notes), d0204 (error: PQ-E4582 RETENTION_CONNECTION_LIMIT_REACHED), d0507 (changelog: PaderQueue 1.1 release notes), d0550 (error: PQ-E3557 REPLICATOR_CONNECTION_LIMIT_REACHED), d0192 (changelog: PaderQueue 2.0 release notes)
- **Missing pieces:** [['d0153']]
- **Classification:** 1 of 1 needed pieces of information not in the top-5 documents
- **Your explanation (why did it fail?):** 
