# Manual check of 10 judge decisions (r4)

For each item read the question, the ground truth and the system answer, decide yourself whether the answer is correct, then compare with the judge. Fill in the last line.

## 1. dev004  [paraphrase]

- **Question:** Which setting controls how many times the mechanism that parks messages nobody could process tries again before it gives up?
- **Ground truth:** The setting `dlq.max_retries`.
- **System answer:** The documentation does not contain this information.
- **Judge correctness:** 0.0  (The answer says the information is unavailable, but the setting is `dlq.max_retries`.)
- **Judge faithfulness:** None   **abstained:** True
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 2. dev042  [multi-hop]

- **Question:** What is the current default value of the setting that the error catalogue recommends changing for PQ-E2051?
- **Ground truth:** `compactor.compression` defaults to `lz4` in 4.x.
- **System answer:** The documentation does not contain this information.
- **Judge correctness:** 0.0  (The answer says the information is unavailable, but the default is `lz4` for `compactor.compression` in 4.x.)
- **Judge faithfulness:** None   **abstained:** True
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 3. dev065  [multi-hop]

- **Question:** Which permanent fix does the documentation recommend for the error that caused incident INC-2025-101?
- **Ground truth:** The incident was caused by PQ-E3177. Fix: Check for connection leaks in clients (connections that are never closed). If the load is legitimate, increase `scheduler.max_connections`.
- **System answer:** The documentation does not contain this information.
- **Judge correctness:** 0.0  (The documentation contains the fix: check for client connection leaks, and if the load is legitimate, increase `scheduler.max_connections`.)
- **Judge faithfulness:** None   **abstained:** True
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 4. dev079  [identifier]

- **Question:** What is the recommended fix for PQ-E1799?
- **Ground truth:** Throttling protects the node. Add capacity or reduce load. As a last resort, raise `retention.threshold_percent`.
- **System answer:** In PaderQueue 4.x, add capacity or reduce load; as a last resort, raise `retention.threshold_percent`.
- **Judge correctness:** 0.5  (It gives the recommended actions but omits that throttling protects the node.)
- **Judge faithfulness:** 1.0   **abstained:** False
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 5. dev085  [version]

- **Question:** In which release did the default of `spool.max_connections` change, and what was it before?
- **Ground truth:** In 3.0; before it was `128`.
- **System answer:** The default changed in 3.0; before that, it was `128`.
- **Judge correctness:** 1.0  (It identifies release 3.0 and the previous default value of 128.)
- **Judge faithfulness:** 1.0   **abstained:** False
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 6. dev095  [unanswerable]

- **Question:** How do I fix error PQ-E2395?
- **Ground truth:** The documentation does not contain this information.
- **System answer:** The documentation does not contain this information.
- **Judge correctness:** 1.0  (It clearly states that the documentation does not contain the information.)
- **Judge faithfulness:** None   **abstained:** True
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 7. dev105  [paraphrase]

- **Question:** Which setting can I use to deactivate the backup mechanism that freezes the state of queues completely?
- **Ground truth:** The setting `snapshotter.enabled`.
- **System answer:** In PaderQueue 4.x, set `snapshotter.enabled = false` to turn off the snapshotter that creates point-in-time queue backups.
- **Judge correctness:** 1.0  (It identifies `snapshotter.enabled` and says to set it to `false` to deactivate queue snapshots.)
- **Judge faithfulness:** 1.0   **abstained:** False
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 8. dev119  [multi-hop]

- **Question:** What is the current default value of the setting that the error catalogue recommends changing for PQ-E1799?
- **Ground truth:** `retention.threshold_percent` defaults to `95` in 4.x.
- **System answer:** The documentation does not contain this information.
- **Judge correctness:** 0.0  (The answer says the information is unavailable, but the default is `95` in 4.x.)
- **Judge faithfulness:** None   **abstained:** True
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 9. dev132  [version]

- **Question:** What was the default value of `quota.batch_size` in PaderQueue 2.x?
- **Ground truth:** `500`
- **System answer:** In PaderQueue 2.x, the default value of `quota.batch_size` was `500`.
- **Judge correctness:** 1.0  (It states that the default value of `quota.batch_size` in PaderQueue 2.x was `500`.)
- **Judge faithfulness:** 1.0   **abstained:** False
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 

## 10. dev137  [unanswerable]

- **Question:** What is the default value of `coordinator.timeout_ms`?
- **Ground truth:** The documentation does not contain this information.
- **System answer:** The documentation does not contain this information.
- **Judge correctness:** 1.0  (The answer clearly states that the documentation does not contain the information.)
- **Judge faithfulness:** None   **abstained:** True
- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** 
