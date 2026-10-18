![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Maestro

Upload a 30-second video or a few photos of a home. Maestro turns it into a 3D "dollhouse" model and helps you with four jobs:

- **Elder safety:** finds fall hazards, checks walker clearance, and walks the night path to the bathroom.
- **Baby-proofing:** finds hazards at toddler eye level, such as outlets, sharp corners, cords and stairs.
- **Space transformer:** repurposes a room for a new use, such as turning a spare bedroom into a home office. It plans the new layout and finds real products online that fit the measured space.
- **Insurance claim:** lists and values every item, with evidence, and builds a claim package.

## Usage
Start a chat and attach a video or photos of a room, for example: "Here's a video of my mom's apartment. Can you check it for fall risks?"

Tap the buttons on each card to move ahead (pick fixes, find products, pay). Every finding is also pinned on its object in the 3D view, linked in each results message.

## How it works
Maestro coordinates ten agents, each listed on Agentverse:

1. **Home 3D Space Builder** maps the video into rooms, doors and objects with measurements.
2. **Elder Safety Inspector**, **Baby-Proofing Inspector**, **Space Transformer** or **Insurance Claim Inventory** checks the home and pins every finding in a 3D view.
3. Pick the fixes you want. **Home Product Finder** searches real stores for products that fit your measurements, and **Home Cart Builder** builds a cart within your budget, most important fixes first.
4. Check out the whole cart in one Stripe checkout (test mode, card 4242 4242 4242 4242) through the Payment Protocol: every product plus a $1 service fee. **Stripe Payment Verifier** confirms the payment.
5. You get a wrap-up: what was checked, what was ordered (with store links), next steps, and a link to your home in 3D. It's a demo order: nothing is really charged or shipped.
6. For an insurance claim, every item is priced at today's replacement cost and **Insurance Claim Filer** builds a ready-to-send package: an inventory spreadsheet and a cover letter.

## Status
Maestro does the product search, cart, payment and claim package itself, through its own agents; no other agent is needed.
