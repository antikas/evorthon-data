# Customer service reporting - verification contract
<!-- evorthon-implements: EVD-README-003 -->

## Contract and evidence

- **Deterministic checks:** schema, population, keys, values, aggregates, replay metadata and published measures are compared.
- **Results:** declared fixtures pass; altered aggregate, missing key and unreconciled population fail.
- **Evidence identity:** `EVD-MOD-040` through `EVD-MOD-043` identify the contract, envelope, negative fixture and accepted publication.
- **Uncertainty:** this record covers synthetic data only.
- **Approved differences:** any difference requires an explicit recorded disposition before acceptance.
- **Named acceptance:** Maya Chen names acceptance when all deterministic checks pass.
- **Evidence identifiers:** `EVD-MOD-040` contract; `EVD-MOD-041` fixed synthetic comparison envelope; `EVD-MOD-042` negative aggregate fixture; `EVD-MOD-043` accepted publication evidence.
- **Checks:** declared schema, population, keys, values, aggregates, permitted replay metadata and final published measures.
- **Negative cases:** altered aggregate, missing key and unreconciled population each fail before publication.
- **Acceptance rule:** a publication is accepted only when all checks pass and Maya Chen names acceptance; differences require an explicit recorded disposition.

## Executed proof

- **Proof:** `tests/product/test_proof_customer_service.py` runs this record as a complete delivery over frozen fixtures and injected fakes.
- **Command:** `python scripts/run_tests.py --lane fast tests/product/test_proof_customer_service.py`
- **Material:** `tests/fixtures/proofs/customer-service-reporting` holds the declared inputs, the reference and lookup datasets, the two approved daily publications, the declared lineage, and one candidate per deliberate defect.
- **Defects:** a repeated grain key, a dropped population, a daily total that moves while every row stays inside its declared tolerance, a carried-back effective date, and a resolution rate rounded at a place the declared scale does not carry. Each is read as the class the product decides; the aggregate-only divergence decides no class, reports unknown and withholds its packet, which leaves that fault open.
- **Result:** both corrected publications reproduce on the corrected rerun, and a restored defect turns it red.
- **Two versions:** the proof cuts two versions of this use case on one record. The first covers one segment and is accepted on wholly synthetic evidence with that label; the second covers every segment and is accepted beside it on the captured publications. The record's lifecycle moves once, at the first acceptance; the first version and the acceptance it was taken through stand exactly as they were taken; and both coverage statements and both evidence provenances are read back off that one record.
- **Named acceptance:** the proof declares its accepting authority as `service-acceptance-authority`; the named acceptor above stands for that authority in the executed run.
- **Uncertainty:** every byte used by the proof is synthetic.

## Paired review

- **Paired review:** completed before named acceptance.
- **Reviewer:** verify-data-platform reviewer.
- **Finding:** acceptance authority was initially absent.
- **Disposition:** resolved: Maya Chen is the sole synthetic acceptance authority.
- **Finding V-02:** replay exclusions were ambiguous.
- **Disposition:** resolved: `EVD-MOD-040` declares the permitted replay fields; all other changes fail.

## Acceptance

Maya Chen accepts the synthetic verification contract.
