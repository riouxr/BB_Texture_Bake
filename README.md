# BB UV Transfer

Bake a high-resolution mesh's texture onto a different-topology low-resolution
mesh. Point it at a detailed source (a sculpt, scan, or any densely textured
mesh) and a separately-topologized target (a clean retopo), and it bakes the
source's shading onto the target's own UVs using Cycles.

## Why

Copying UV *coordinates* between meshes of different topology breaks down
wherever the source surface folds close to itself (collars, cuffs, hair,
wrinkles) — any point-proximity match becomes ambiguous and scrambles the
result. Baking sidesteps this: it samples color in image space along the
target's own surface, so an occasional wrong-surface sample shows up as a
small local smudge instead of corrupting the UV layout.

## Install

Blender 4.5 or newer.

1. Download `BB_UV_Transfer.zip` from
   [Releases](https://github.com/riouxr/BB_UV_Transfer/releases).
2. **Edit > Preferences > Add-ons > Install from Disk**, pick the zip.

## Use

1. **View3D > N-panel > Tool > BB UV Transfer**.
2. Set **High Res** to the detailed source mesh (must have a node-based
   material with its texture wired to Base Color).
3. Set **Low Res** to the target mesh. If it has no `UVMap` yet, one is
   created automatically with Smart UV Project.
4. Adjust bake settings if needed:
   - **Image Size** / **Margin** — output resolution and island padding.
   - **Max Ray Distance** — how far to search for the high-res surface.
     Keep it small, just above the real gap between the two meshes, so it
     doesn't reach across nearby folds or unrelated geometry.
   - **Cage Extrusion** — pushes the low-res surface outward before casting
     rays, which helps when the two meshes nearly touch.
   - **Save Next to Blend File** (on by default) saves the baked PNG beside
     the `.blend`; uncheck it to pick a custom path instead.
5. Press **Bake High Res to Low Res**.

The target gets its own dedicated material for the bake — if it currently
shares a material with the source, a new one is created automatically rather
than writing into (and corrupting) the shared node tree.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
