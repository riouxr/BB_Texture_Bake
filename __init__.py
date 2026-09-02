bl_info = {
    "name": "BB Texture Bake",
    "author": "Blender Bob",
    "version": (3, 1, 1),
    "blender": (4, 5, 0),
    "location": "3D View > Sidebar > Tool",
    "description": "Bake a high-resolution mesh's Base Color/Roughness/Normal onto a different-topology low-resolution mesh",
    "category": "Material",
}

import bpy
import os


class BBTB_Settings(bpy.types.PropertyGroup):
    source: bpy.props.PointerProperty(
        name="High Res",
        description="Detailed mesh to bake the texture from",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH',
    )
    target: bpy.props.PointerProperty(
        name="Low Res",
        description="Mesh to bake the texture onto",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH',
    )
    name_from_target: bpy.props.BoolProperty(
        name="Name From Target",
        default=True,
        description="Use the Low Res object's name as the base image name "
                     "(e.g. Retopo_D, Retopo_N). Uncheck to set a custom name below",
    )
    image_name: bpy.props.StringProperty(
        name="Image Name",
        default="BakedTexture",
    )
    image_size: bpy.props.IntProperty(
        name="Image Size",
        default=2048,
        min=64,
        soft_max=8192,
    )
    margin: bpy.props.IntProperty(
        name="Margin",
        default=16,
        min=0,
        soft_max=64,
        description="Pixels to extend the baked result past UV island edges",
    )
    max_ray_distance: bpy.props.FloatProperty(
        name="Max Ray Distance",
        default=0.02,
        min=0.0,
        soft_max=1.0,
        description="How far to search for the high-res surface. 0 = unlimited. "
                     "Keep this small and just above the real gap between the meshes "
                     "to avoid picking up nearby folds/other surfaces",
    )
    cage_extrusion: bpy.props.FloatProperty(
        name="Cage Extrusion",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        description="Pushes the low-res surface outward before casting rays, which "
                     "avoids self-occlusion artifacts when the two meshes nearly touch",
    )
    save_next_to_blend: bpy.props.BoolProperty(
        name="Save Next to Blend File",
        default=True,
        description="Save the baked image (PNG) in the same folder as this .blend file",
    )
    save_path: bpy.props.StringProperty(
        name="Save To",
        subtype='FILE_PATH',
        description="File path to save the baked image to (PNG)",
    )


def find_node(material, name):
    for node in material.node_tree.nodes:
        if node.name == name:
            return node
    return None


# (suffix, BSDF input to check on the source / wire up on the target, bake type,
# pass filter, image colorspace)
BAKE_CHANNELS = (
    ("D", "Base Color", 'DIFFUSE', {'COLOR'}, 'sRGB'),
    ("R", "Roughness", 'ROUGHNESS', set(), 'Non-Color'),
    ("N", "Normal", 'NORMAL', set(), 'Non-Color'),
)


class BBTB_OT_bake(bpy.types.Operator):
    bl_idname = "bb_texture_bake.bake"
    bl_label = "Bake High Res to Low Res"
    bl_description = "Bake the high-res mesh's texture onto the low-res mesh's UVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.bb_texture_bake_settings
        source = s.source
        target = s.target

        if not source or not target:
            self.report({'ERROR'}, "Set both High Res and Low Res.")
            return {'CANCELLED'}
        if source == target:
            self.report({'ERROR'}, "High Res and Low Res must be different objects.")
            return {'CANCELLED'}
        if source.type != 'MESH' or target.type != 'MESH':
            self.report({'ERROR'}, "Both objects must be meshes.")
            return {'CANCELLED'}
        if not source.active_material or not source.active_material.use_nodes:
            self.report({'ERROR'}, "High Res needs a node-based material with its texture connected.")
            return {'CANCELLED'}

        source_bsdf = next(
            (n for n in source.active_material.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled'),
            None,
        )
        if source_bsdf is None:
            self.report({'ERROR'}, "High Res needs a Principled BSDF in its material.")
            return {'CANCELLED'}

        channels = [ch for ch in BAKE_CHANNELS if source_bsdf.inputs[ch[1]].is_linked]
        if not channels:
            self.report({'ERROR'}, "High Res has no textures connected to Base Color, Roughness, or Normal.")
            return {'CANCELLED'}

        uv_name = "UVMap"
        dst_mesh = target.data
        dst_uv = dst_mesh.uv_layers.get(uv_name)
        created_uv = dst_uv is None

        prev_selected = list(context.selected_objects)
        prev_active = context.view_layer.objects.active
        prev_mode = context.object.mode if context.object else 'OBJECT'
        if prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        if created_uv:
            for ob in context.view_layer.objects:
                ob.select_set(False)
            target.select_set(True)
            context.view_layer.objects.active = target

            if len(dst_mesh.uv_layers) == 0:
                # Entering Edit mode on a mesh with zero UV layers auto-creates one
                # named "UVMap" already, so nothing needs to be added by hand.
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                # The mesh has other UV layers already; add the named one ourselves.
                # Setting it active while still in Object mode doesn't reliably carry
                # over into Edit mode, so it's re-asserted again right after switching.
                dst_uv = dst_mesh.uv_layers.new(name=uv_name)
                dst_mesh.uv_layers.active = dst_uv
                bpy.ops.object.mode_set(mode='EDIT')
                dst_mesh.uv_layers.active = dst_uv

            bpy.ops.mesh.select_all(action='SELECT')
            # A lower angle limit than the default trades more (smaller, less
            # distorted) islands for much tighter packing; followed by an explicit
            # pack pass with rotation and exact-shape packing, since Smart UV
            # Project's own packing leaves a lot of the UV square empty otherwise.
            bpy.ops.uv.smart_project(
                angle_limit=0.87266,  # 50 degrees
                island_margin=0.01,
                correct_aspect=True,
            )
            bpy.ops.uv.pack_islands(
                rotate=True,
                rotate_method='ANY',
                scale=True,
                margin=0.001,
                shape_method='CONCAVE',
            )
            bpy.ops.object.mode_set(mode='OBJECT')
            dst_uv = dst_mesh.uv_layers.get(uv_name)

        dst_mesh.uv_layers.active = dst_uv

        image_name = target.name if s.name_from_target else (s.image_name.strip() or "BakedTexture")

        mat = target.active_material
        if mat is None or mat == source.active_material:
            # Never bake into a material shared with the source object: writing the
            # bake node/link into a shared node tree would also corrupt the source's
            # own shading, since they'd be the same datablock.
            mat = bpy.data.materials.new(name=f"{target.name}_BB_Bake")
            mat.use_nodes = True
            if target.data.materials:
                target.data.materials[0] = mat
            else:
                target.data.materials.append(mat)
        elif not mat.use_nodes:
            mat.use_nodes = True

        target_bsdf = next((n for n in mat.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled'), None)
        if target_bsdf is None:
            # The material exists but has no Principled BSDF (e.g. just a bare
            # Material Output) -- without one there's nothing to wire the bake
            # results into, so create one and hook it up.
            target_bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            target_bsdf.location = (-50, 300)
            output_node = next((n for n in mat.node_tree.nodes if n.bl_idname == 'ShaderNodeOutputMaterial'), None)
            if output_node is None:
                output_node = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
                output_node.location = (250, 300)
            mat.node_tree.links.new(target_bsdf.outputs["BSDF"], output_node.inputs["Surface"])

        prev_engine = context.scene.render.engine
        context.scene.render.engine = 'CYCLES'

        for ob in context.view_layer.objects:
            ob.select_set(False)
        source.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target

        baked_images = []
        try:
            with context.temp_override(
                active_object=target,
                selected_objects=[source, target],
                selected_editable_objects=[source, target],
            ):
                for suffix, input_name, bake_type, pass_filter, colorspace in channels:
                    image = bpy.data.images.new(
                        f"{image_name}_{suffix}", width=s.image_size, height=s.image_size, alpha=False,
                    )
                    image.colorspace_settings.name = colorspace

                    node_name = f"BB_Texture_Bake_{suffix}"
                    bake_node = find_node(mat, node_name)
                    if bake_node is None:
                        bake_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                        bake_node.name = node_name
                    bake_node.image = image
                    bake_node.location = (-600, 300 - 300 * len(baked_images))
                    # Cycles requires the bake target node to be both the active
                    # node AND selected -- nodes.active alone isn't enough once
                    # the material has more than a couple of nodes.
                    for n in mat.node_tree.nodes:
                        n.select = False
                    bake_node.select = True
                    mat.node_tree.nodes.active = bake_node

                    bake_result = bpy.ops.object.bake(
                        type=bake_type,
                        pass_filter=pass_filter,
                        use_selected_to_active=True,
                        max_ray_distance=s.max_ray_distance,
                        cage_extrusion=s.cage_extrusion,
                        margin=s.margin,
                        use_clear=True,
                    )
                    if 'FINISHED' not in bake_result:
                        bpy.data.images.remove(image)
                        self.report({'ERROR'}, f"Baking {input_name} failed.")
                        return {'CANCELLED'}

                    if input_name == "Normal":
                        normal_map_node = find_node(mat, "BB_Texture_Bake_NormalMap")
                        if normal_map_node is None:
                            normal_map_node = mat.node_tree.nodes.new("ShaderNodeNormalMap")
                            normal_map_node.name = "BB_Texture_Bake_NormalMap"
                            normal_map_node.location = (-250, -300)
                        normal_map_node.uv_map = uv_name
                        mat.node_tree.links.new(bake_node.outputs["Color"], normal_map_node.inputs["Color"])
                        mat.node_tree.links.new(normal_map_node.outputs["Normal"], target_bsdf.inputs["Normal"])
                    else:
                        mat.node_tree.links.new(bake_node.outputs["Color"], target_bsdf.inputs[input_name])

                    baked_images.append((suffix, image))
        finally:
            context.scene.render.engine = prev_engine
            for ob in context.view_layer.objects:
                ob.select_set(ob in prev_selected)
            context.view_layer.objects.active = prev_active
            if prev_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=prev_mode)

        blend_saved = bool(bpy.data.filepath)
        if s.save_next_to_blend and not blend_saved:
            self.report({'WARNING'}, "Blend file isn't saved yet; packing the images instead.")

        custom_base = s.save_path.strip()
        if custom_base.lower().endswith(".png"):
            custom_base = custom_base[:-4]

        for suffix, image in baked_images:
            if s.save_next_to_blend and blend_saved:
                save_path = os.path.join(os.path.dirname(bpy.data.filepath), f"{image_name}_{suffix}.png")
            elif not s.save_next_to_blend and custom_base:
                save_path = f"{custom_base}_{suffix}.png"
            else:
                save_path = ""

            if save_path:
                image.filepath_raw = bpy.path.abspath(save_path)
                image.file_format = 'PNG'
                image.save()
            else:
                image.pack()

        baked_names = ", ".join(f"{image_name}_{suffix}" for suffix, _ in baked_images)
        self.report({'INFO'}, f"Baked {baked_names} ({s.image_size}x{s.image_size}) onto {target.name}.")
        return {'FINISHED'}


class BBTB_PT_panel(bpy.types.Panel):
    bl_label = "BB Texture Bake"
    bl_idname = "BBTB_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        s = context.scene.bb_texture_bake_settings

        box = layout.box()
        box.label(text="Source Texture")
        box.prop(s, "source", text="High Res")

        box = layout.box()
        box.label(text="Target")
        box.prop(s, "target", text="Low Res")

        box = layout.box()
        box.label(text="Bake Settings")
        box.prop(s, "name_from_target")
        if not s.name_from_target:
            box.prop(s, "image_name")
        box.prop(s, "image_size")
        box.prop(s, "margin")
        box.prop(s, "max_ray_distance")
        box.prop(s, "cage_extrusion")
        box.prop(s, "save_next_to_blend")
        if not s.save_next_to_blend:
            box.prop(s, "save_path")

        row = layout.row()
        row.scale_y = 1.5
        row.operator("bb_texture_bake.bake", icon='RENDER_STILL')


classes = (BBTB_Settings, BBTB_OT_bake, BBTB_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bb_texture_bake_settings = bpy.props.PointerProperty(type=BBTB_Settings)


def unregister():
    del bpy.types.Scene.bb_texture_bake_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
