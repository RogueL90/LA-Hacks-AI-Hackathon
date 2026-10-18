![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Home 3D Space Builder

Turns a 30-second video or a few photos of a home into a 3D "dollhouse" model. Every object in the model is real data: its type, size, position and color, with the video frame it was seen in.

## Messages
- In: `SpaceBuildRequest` with the public URLs of the video or photos
- Out: `SpaceBuildResult` with the `Space`: rooms, doors, objects, scale method, a 3D viewer link and a snapshot image

Part of Maestro; reached through the Maestro coordinator in ASI:One.
