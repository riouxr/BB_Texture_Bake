bl_info = {
    "name": "BB UV Transfer",
    "author": "Blender Bob",
    "version": (2, 2, 0),
    "blender": (4, 5, 0),
    "location": "3D View > Sidebar > Tool",
    "description": "Bake a high-resolution mesh's texture onto a different-topology low-resolution mesh",
    "category": "UV",
}

import bpy
import os


class BBUT_Settings(bpy.types.PropertyGroup):
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


def find_image_node(material):
    for node in material.node_tree.nodes:
        if node.bl_idname == 'ShaderNodeTexImage' and node.name == "BB_UV_Transfer_BakeTarget":
            return node
    return None


class BBUT_OT_bake(bpy.types.Operator):
    bl_idname = "bb_uv_transfer.bake"
    bl_label = "Bake High Res to Low Res"
    bl_description = "Bake the high-res mesh's texture onto the low-res mesh's UVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.bb_uv_transfer_settings
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

        image_name = s.image_name.strip() or "BakedTexture"
        image = bpy.data.images.new(image_name, width=s.image_size, height=s.image_size, alpha=False)

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

        bake_node = find_image_node(mat)
        if bake_node is None:
            bake_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            bake_node.name = "BB_UV_Transfer_BakeTarget"
            bake_node.location = (-400, 300)
        bake_node.image = image
        mat.node_tree.nodes.active = bake_node

        bsdf = next((n for n in mat.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled'), None)
        if bsdf is not None:
            mat.node_tree.links.new(bake_node.outputs["Color"], bsdf.inputs["Base Color"])

        prev_engine = context.scene.render.engine
        context.scene.render.engine = 'CYCLES'

        for ob in context.view_layer.objects:
            ob.select_set(False)
        source.select_set(True)
        target.select_set(True)
        context.view_layer.objects.active = target

        try:
            with context.temp_override(
                active_object=target,
                selected_objects=[source, target],
                selected_editable_objects=[source, target],
            ):
                result = bpy.ops.object.bake(
                    type='DIFFUSE',
                    pass_filter={'COLOR'},
                    use_selected_to_active=True,
                    max_ray_distance=s.max_ray_distance,
                    cage_extrusion=s.cage_extrusion,
                    margin=s.margin,
                    use_clear=True,
                )
        finally:
            context.scene.render.engine = prev_engine
            for ob in context.view_layer.objects:
                ob.select_set(ob in prev_selected)
            context.view_layer.objects.active = prev_active
            if prev_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=prev_mode)

        if 'FINISHED' not in result:
            bpy.data.images.remove(image)
            self.report({'ERROR'}, "Bake failed.")
            return {'CANCELLED'}

        if s.save_next_to_blend:
            if bpy.data.filepath:
                save_path = os.path.join(os.path.dirname(bpy.data.filepath), image_name + ".png")
            else:
                save_path = ""
                self.report({'WARNING'}, "Blend file isn't saved yet; packing the image instead.")
        else:
            save_path = s.save_path.strip()

        if save_path:
            if not save_path.lower().endswith(".png"):
                save_path += ".png"
            image.filepath_raw = bpy.path.abspath(save_path)
            image.file_format = 'PNG'
            image.save()
        else:
            image.pack()

        self.report({'INFO'}, f"Baked '{image_name}' ({s.image_size}x{s.image_size}) onto {target.name}.")
        return {'FINISHED'}


class BBUT_PT_panel(bpy.types.Panel):
    bl_label = "BB UV Transfer"
    bl_idname = "BBUT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        s = context.scene.bb_uv_transfer_settings

        box = layout.box()
        box.label(text="Source Texture")
        box.prop(s, "source", text="High Res")

        box = layout.box()
        box.label(text="Target")
        box.prop(s, "target", text="Low Res")

        box = layout.box()
        box.label(text="Bake Settings")
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
        row.operator("bb_uv_transfer.bake", icon='RENDER_STILL')


classes = (BBUT_Settings, BBUT_OT_bake, BBUT_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bb_uv_transfer_settings = bpy.props.PointerProperty(type=BBUT_Settings)


def unregister():
    del bpy.types.Scene.bb_uv_transfer_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
