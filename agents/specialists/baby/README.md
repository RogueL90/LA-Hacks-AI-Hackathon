![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Baby-Proofing Inspector

Finds hazards a toddler can reach in a 3D model of a home: anything below 0.9 m (about 3 ft).

## What it checks
- Uncovered outlets, cords and floor plants within reach
- Tall or unanchored furniture and TVs that can tip over (CPSC Anchor It!)
- Sharp corners at a toddler's head height

## Messages
- In: `ModeRequest` (mode `baby`) with the child's age and a budget
- Out: `ModeResult` with hazards, fixes and a product search for each fix

Part of Last Mile Home; reached through the Last Mile Home coordinator in ASI:One.
