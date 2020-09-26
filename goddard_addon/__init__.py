bl_info = {
    "name": "SM64 Goddard Editor Addon",
    "author": "SI Silicon",
    "blender": (2, 90, 0),
    "location": "View3D > Goddard",
    "category": "Object",
}

import bpy
import sys
import os
import imp

debug = __name__ == "__main__"

if debug:
    dir = os.path.dirname(bpy.data.filepath)
    if not dir in sys.path:
        sys.path.append(dir)

from . import import_goddard
from . import export_goddard

imp.reload(import_goddard)
imp.reload(export_goddard)
    
from bpy.props import (StringProperty, PointerProperty, BoolProperty)

from bpy.types import (
   Panel,
   Menu,
   Operator,
   PropertyGroup
)


class GoddardProperties(PropertyGroup):
    source_dir: StringProperty(
        name="Source Directory",
        description="The directory in which the SM64 source code is located.",
        subtype= 'DIR_PATH'
    )
    c_memory_management: BoolProperty(
        name="C Memory Management",
        description="Replaces goddard's memory manager with C's builtin own.\nEnable this to be able to export higher poly goddard IF YOU NEED TO."
    )


class ImportGoddard(Operator):
    bl_label = "Import Goddard from SM64"
    bl_idname = "gd.import_goddard"
    bl_description = "Import the goddard head from the source code.\nDo this to get a base for editing."

    def execute(self, context):
        return import_goddard.execute(self, context)


class ExportGoddard(Operator):
    bl_label = "Export Goddard to SM64"
    bl_idname = "gd.export_goddard"
    bl_description = "Export the head to a goddard folder in the root of the SM64 folder.\nYou must then apply it by moving said folder into the `src` folder."

    def execute(self, context):
        return export_goddard.exceute(self, context)


class GoddardUI(Panel):
    bl_label = "Goddard Import Export"
    bl_idname = "OBJECT_PT_goddard_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Goddard'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        gd = scene.goddard
        
        layout.prop(gd, "source_dir")
        layout.prop(gd, "c_memory_management")

        layout.operator("gd.import_goddard")
        layout.operator("gd.export_goddard")

classes = (
    ImportGoddard,
    ExportGoddard,
    GoddardProperties,
    GoddardUI
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bpy.types.Scene.goddard = PointerProperty(type=GoddardProperties)

def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.Scene.goddard


# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if debug:
    register()