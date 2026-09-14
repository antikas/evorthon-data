# Renewable asset observability - verification contract

## Contract and evidence

- **Deterministic checks:** identity, event-time, measurement range, metric, alert-severity and consumer-view invariants are checked.
- **Results:** valid fixtures pass; unknown identity, invalid range and unowned severity fail.
- **Evidence identity:** `EVD-GRN-030` through `EVD-GRN-033` identify the contract, fixtures and consumer-view evidence.
- **Uncertainty:** this record covers synthetic data only.
- **Approved differences:** any proposed difference requires an explicit disposition before acceptance.
- **Named acceptance:** Elena Brooks names acceptance when the declared checks pass.
- **Evidence identifiers:** `EVD-GRN-030` contract; `EVD-GRN-031` synthetic event fixture; `EVD-GRN-032` unknown-identity negative fixture; `EVD-GRN-033` accepted consumer view.
- **Checks:** source contract, asset identity, event-time validity, measurement range, declared metric calculation, alert severity and consumer-view invariants.
- **Negative cases:** unknown asset identity, invalid range and unowned alert severity fail.
- **Greenfield boundary:** conformance verification evaluates the declared contract. No current estate or legacy/parity baseline is asserted.
- **Acceptance rule:** all contract checks pass and Elena Brooks names acceptance.

## Executed proof

- **Proof:** `tests/product/test_proof_renewable_asset.py` runs this record as a complete delivery over frozen fixtures and injected fakes.
- **Command:** `python scripts/run_tests.py --lane fast tests/product/test_proof_renewable_asset.py`
- **Material:** `tests/fixtures/proofs/renewable-asset-observability` holds the declared input, reference and enrichment constraints, the two approved golden views, the declared requirements of the contract families, the declared lineage, and one candidate per deliberate defect.
- **Defects:** the proof covers an interface version absent from the approved contract and observations outside the declared measurement range. It also covers a feed run that missed the declared cutoff, an earlier register snapshot with unmatched asset codes, and capacity factors that move by one unit in the last declared decimal place. Each is answered by the family that owns it.
- **Result:** the difference between published rows is diagnosed, advised on, disposed of by the named authority, and reproduced green on the corrected candidate; a restored defect turns the rerun red. The four families have no failing output, so row-level diagnosis reports no class.
- **Two versions:** the proof cuts two versions of this use case on one record. The first covers one published view and is accepted; the second covers every segment and is accepted beside it. The record's lifecycle moves once, at the first acceptance, and the first version and the acceptance it was taken through stand exactly as they were taken.
- **Greenfield boundary:** every approved golden view is authored from the approved specification and carries that origin. The engagement refuses questions about outputs of earlier estates. The case refuses expected values taken from a run of one.
- **Uncertainty:** every byte used by the proof is synthetic.

## Paired review

- **Paired review:** completed before named acceptance.
- **Reviewer:** verify-data-platform reviewer.
- **Finding:** disclosure wording was missing.
- **Disposition:** resolved: `EVD-GRN-030` defines the contract-owned field-disclosure policy.
- **Finding V-02:** a reviewer could mistake fixtures for a baseline.
- **Disposition:** resolved: fixtures demonstrate contract conformance.

## Acceptance

Elena Brooks accepts the synthetic greenfield verification contract.
