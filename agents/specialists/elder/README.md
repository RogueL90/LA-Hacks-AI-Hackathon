![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Last Mile Home: Elder Safety

Finds fall hazards in a 3D model of a home, focused on the walk an older person takes at night from bed to the bathroom.

## What it checks
- Clear width along the path and through doors, against what a walker or wheelchair needs (ADA: 32 in, 36 in)
- Loose rugs and cords on the path, lighting for night trips (CDC STEADI "Check for Safety")
- Toilet seat height and grab bars at the tub and toilet

## Messages
- In: `ModeRequest` (mode `elder`) with a profile: person, age, mobility aid, night trips, budget
- Out: `ModeResult` with hazards, measurements, fixes and a product search for each fix

Part of Last Mile Home; reached through the Last Mile Home coordinator in ASI:One.
