# Verification contract — renewable asset observability

## Contract and evidence

- **Deterministic checks:** identity, event-time, measurement range, metric, alert-severity and consumer-view invariants are checked.
- **Results:** valid fixtures pass; unknown identity, invalid range and unowned severity fail.
- **Evidence identity:** `EVD-GRN-030` through `EVD-GRN-033` identify the contract, fixtures and consumer-view evidence.
- **Uncertainty:** this synthetic record does not claim a live-system result.
- **Approved differences:** any proposed difference requires an explicit disposition before acceptance.
- **Named acceptance:** Elena Brooks names acceptance when the declared checks pass.
- **Evidence identifiers:** `EVD-GRN-030` contract; `EVD-GRN-031` synthetic event fixture; `EVD-GRN-032` unknown-identity negative fixture; `EVD-GRN-033` accepted consumer view.
- **Checks:** source contract, asset identity, event-time validity, measurement range, declared metric calculation, alert severity and consumer-view invariants.
- **Negative cases:** unknown asset identity, invalid range and unowned alert severity fail.
- **Greenfield boundary:** this is conformance verification only; no current estate or legacy/parity baseline is asserted.
- **Acceptance rule:** all contract checks pass and Elena Brooks names acceptance.

## Executed proof

- **Proof:** `tests/product/test_proof_renewable_asset.py` runs this record as a complete delivery over frozen fixtures and injected fakes, so the example is executed rather than described.
- **Command:** `python scripts/run_tests.py --lane fast tests/product/test_proof_renewable_asset.py`
- **Material:** `tests/fixtures/proofs/renewable-asset-observability` holds the declared input, reference and enrichment constraints, the two approved golden views, the declared requirements of the contract families, the declared lineage, and one candidate per deliberate defect.
- **Defects:** an interface version the approved contract does not name, observations outside the declared measurement range, a feed run that did not finish before the declared cutoff, an earlier register snapshot that left asset codes unmatched, and capacity factors that move by one unit in the last declared decimal place. Each is answered by the family that owns it, and no other family moves.
- **Result:** the difference between published rows is diagnosed, advised on, disposed of by the named authority and reproduced green on the corrected candidate; a restored defect turns the rerun red. The four families answered over declared facts name no failing output, so the row-level diagnosis has nothing to answer for, and the route says so rather than deciding a class it cannot decide.
- **Two versions:** the proof cuts two versions of this use case on one record. The first covers one published view and is accepted; the second covers every segment and is accepted beside it. The record's lifecycle moves once, at the first acceptance, and the first version and the acceptance it was taken through stand exactly as they were taken.
- **Greenfield boundary:** every approved golden view is authored from the approved specification and carries that origin, the engagement refuses a question about an output of an earlier estate, and the case refuses an expected value taken from a run of one.
- **Uncertainty:** every byte the proof runs on is invented; it does not claim a live-system result.

## Paired review

- **Paired review:** completed before named acceptance.
- **Reviewer:** verify-data-platform reviewer.
- **Finding:** disclosure wording was missing.
- **Disposition:** resolved — field disclosure is a contract-owned policy in `EVD-GRN-030`.
- **Finding V-02:** a reviewer could mistake fixtures for a baseline.
- **Disposition:** resolved — fixtures demonstrate contract conformance and cannot claim parity.

## Acceptance

Elena Brooks accepts the synthetic greenfield verification contract.
