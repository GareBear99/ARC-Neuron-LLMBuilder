# ARC Knowledge Preservation Doctrine

Status: canonical production doctrine for the 3.0 roadmap.

## Prime rule

ARC-Neuron must build knowledge without destroying, hiding, overwriting, or misconstruing the path that produced that knowledge.

A model improvement is not complete unless the system can still answer:

1. What source data influenced the behavior?
2. Which transform produced the training record?
3. Which candidate consumed it?
4. Which benchmark measured it?
5. Which gate accepted or rejected it?
6. Which artifact, receipt, or rollback path proves the decision?

## Non-destruction law

No training, merge, compression, distillation, benchmark, promotion, cleanup, or archive step may replace prior evidence without preserving a cryptographic or content-addressed path back to the earlier state.

## Required preservation surfaces

Every governed learning event should preserve:

- source manifest
- dataset manifest
- transform manifest
- candidate manifest
- benchmark manifest
- scoring report
- promotion or rejection receipt
- archive pointer
- rollback pointer
- license classification
- operator notes when human judgment was involved

## Candidate isolation law

New data classes must not directly write into the incumbent lane. They must enter a candidate class first, then prove they improve target capabilities without breaching protected floors.

## Truth hierarchy

1. Sealed receipts and hashes
2. Reproducible benchmark outputs
3. Dataset manifests and license records
4. Source documents and operator corrections
5. Narrative changelog claims

If the changelog disagrees with reproducible receipts, the receipts win.

## Plain-English purpose

ARC-Neuron should never merely become smarter. It should know how it became smarter, preserve that path, and be able to roll back if the path was wrong.
