# BB Texture Bake

Bake a high-resolution mesh's Base Color, Roughness, and Normal maps onto a
different-topology low-resolution mesh. Point it at a detailed source (a
sculpt, scan, or any densely textured mesh) and a separately-topologized
target (a clean retopo), and it bakes whichever of those channels the
source's material actually has connected, onto the target's own UVs, using
Cycles.

## Why

Copying UV *coordinates* between meshes of different topology breaks down
wherever the source surface folds close to itself (collars, cuffs, hair,
wrinkles) — any point-proximity match becomes ambiguous and scrambles the
result. Baking sidesteps this: it samples each channel in image space along
the target's own surface, so an occasional wrong-surface sample shows up as
a small local smudge instead of corrupting the UV layout.

## Install

Blender 4.5 or newer.

1. Download `BB_Texture_Bake.zip` from
   [Releases](https://github.com/riouxr/BB_Texture_Bake/releases).
2. **Edit > Preferences > Add-ons > Install from Disk**, pick the zip.

## Use

1. **View3D > N-panel > Tool > BB Texture Bake**.
2. Set **High Res** to the detailed source mesh (its material needs a
   Principled BSDF with Base Color, Roughness, and/or Normal wired up —
   only the channels that are actually connected get baked).
3. Set **Low Res** to the target mesh. If it has no `UVMap` yet, one is
   created automatically with Smart UV Project + a tight repack.
4. Adjust bake settings if needed:
   - **Image Size** / **Margin** — output resolution and island padding.
   - **Max Ray Distance** — how far to search for the high-res surface.
     Keep it small, just above the real gap between the two meshes, so it
     doesn't reach across nearby folds or unrelated geometry.
   - **Cage Extrusion** — pushes the low-res surface outward before casting
     rays, which helps when the two meshes nearly touch.
   - **Save Next to Blend File** (on by default) saves the baked PNGs
     beside the `.blend`, named `<Image Name>_D` / `_R` / `_N`; uncheck it
     to pick a custom path instead.
5. Press **Bake High Res to Low Res**.

The target gets its own dedicated material for the bake — if it currently
shares a material with the source, a new one is created automatically
rather than writing into (and corrupting) the shared node tree. Each baked
channel is wired straight into a Principled BSDF on that material (Normal
goes through a Normal Map node), so the result is a ready-to-use material,
not just loose image files.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
