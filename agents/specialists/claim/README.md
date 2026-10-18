![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Insurance Claim Inventory

Turns a 3D model of a home into a contents inventory for an insurance claim.

## What it does
- Lists every item (furniture, electronics, decor), skipping fixtures that belong to the building
- Keeps the evidence for each item and flags low-confidence items for the owner to confirm
- Prepares a replacement-price search for each item; values come from current prices or the owner, never guesses

## Messages
- In: `ModeRequest` (mode `claim`) with the policy type and ZIP code
- Out: `ModeResult` with one item per object, ready for pricing and the claim package

Part of Maestro; reached through the Maestro coordinator in ASI:One.
