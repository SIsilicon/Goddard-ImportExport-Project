
import bpy
import ast
import os
import sys
import re
import math
from mathutils import Matrix, Vector, Euler
from .dynlist_utils import tokenize_list

D_MATERIAL = bpy.types.Material
D_LIGHT = bpy.types.Light

id_database = {}

current_mat = None
current_object = None

current_context = None
vertex_count = 0

def select_object(object):
    object.select_set(True)
    current_context.view_layer.objects.active = object

def MakeDynObj(type, meta):
    global current_mat
    global current_object

    if type == D_MATERIAL:
        current_mat = bpy.data.materials.new(name = "n64_mat")
    elif type == D_LIGHT:
        current_mat = None
        current_object = bpy.data.objects.new("n64_light", bpy.data.lights.new(name = "Light", type = "POINT"))
        current_context.collection.objects.link(current_object)
        select_object(current_object)

def SetId(id):
    global current_object
    global current_mat

    if current_mat:
        if len(current_object.data.materials) > id:
            current_object.data.materials[id] = current_mat
        else:
            current_object.data.materials.append(current_mat)
    else:
        id_database[id] = current_object

def SetShapePtrPtr(null_arg):
    pass

def SetAmbient(r, g, b):
    pass #print(["SetAmbient", r, g, b])

def SetDiffuse(r, g, b):
    if current_mat:
        current_mat.diffuse_color = (r, g, b, 1.0)
    else:
        current_object.color = (r, g, b, 1.0)

def SetFlag(null_arg):
    pass


def load_dynlist(filepath, vertex_data, face_data):
    global vertex_count
    if not os.path.exists(filepath):
        return None

    obj = None
    with open(filepath) as file:
        text = file.read()
        
        # Load vertices
        vertex_list = []
        arr_start1 = text.find(vertex_data + " = ")
        if arr_start1 != -1:
            arr_start1 += len(vertex_data + " = ")
            arr_end1 = text.find("};", arr_start1) + 1
            v_l = text[arr_start1:arr_end1].replace("{", "[").replace("}", "]")
            vertex_list = ast.literal_eval(v_l)
            vertex_count += len(vertex_list)
            vertex_list = [val for sublist in vertex_list for val in sublist]
            for idx, _ in enumerate(vertex_list):
                vertex_list[idx] /= 212.77
        else:
            print("Couldn't find vertex data!")
            
        # Load faces and material indices
        face_list = []
        mat_id_list = []
        arr_start2 = text.find(face_data + " = ")
        if arr_start2 != -1:
            arr_start2 += len(face_data + " = ")
            arr_end2 = text.find("};", arr_start2) + 1
            face_list = ast.literal_eval(text[arr_start2:arr_end2].replace("{", "[").replace("}", "]"))
            temp_list = []
            for idx, face in enumerate(face_list):
                temp_list.append(face[1:4])
                mat_id_list.append(face[0])
            face_list = [val for sublist in temp_list for val in sublist]
        else:
            print("Couldn't find face data!")
        
        # Apply vertices
        mesh = bpy.data.meshes.new(name='Mario Head Mesh')
        mesh.vertices.add(len(vertex_list) / 3)
        mesh.vertices.foreach_set("co", vertex_list)
        
        # Apply Triangles
        mesh.loops.add(len(face_list))
        mesh.loops.foreach_set("vertex_index", face_list)
        mesh.polygons.add(len(face_list) / 3)
        mesh.polygons.foreach_set("loop_start", range(0, len(face_list), 3))
        mesh.polygons.foreach_set("loop_total", [3] * math.floor(len(face_list) / 3))
        mesh.polygons.foreach_set("material_index", mat_id_list)
        
        mesh.update()
        mesh.validate()
        
        # Create Object whose Object Data is our new mesh
        global current_object
        obj = bpy.data.objects.new('Mario Head', mesh)
        current_object = obj
        
        # Load Materials
        arr_start3 = text.find("MakeDynObj(D_MATERIAL", arr_start2)
        if arr_start3 != -1:
            arr_end3 = text.find("EndGroup", arr_start3) - 1
            dynlist = text[arr_start3:arr_end3].replace(",\n", "\n").replace(" ", "")
            exec(dynlist)
        
        # Add Object to the scene
        current_context.collection.objects.link(obj)

        select_object(obj)
        bpy.ops.object.shade_smooth()
    
    return obj


def load_data_from_master_list(filepath, objects):
    with open(filepath) as file:
        text = file.read()
        
        dynlist = tokenize_list(text)
        
        mesh_weights = {}
        curr_armature = None
        curr_mesh = None
        curr_bone = None
        curr_bone_idx = 0
        curr_weights = []
        curr_object = None

        bone_armature_map = {}

        obj_id_map = {
            "face": 0xE1, "eyebrow.L": 0x3B,
            "eyebrow.R": 0x5D, "mustache": 0x19
        }
        bone_id_map = {
            0xD7: "eye.L", 0xCE: "eye.R",
            0xC5: "face?", 0xC2: "jaw",
            0xB9: "nose", 0xB0: "ear.L",
            0xA7: "ear.R", 0x9E: "cheek.L",
            0x95: "cheek.R", 0x8C: "upper_lip",
            0x83: "forehead", 0x6A: "root?",
            0x0F: "mustache.L", 0x06: "mustache.R",
            0x53: "eyebrow.L.L", 0x4A: "eyebrow.R.L",
            0x41: "eyebrow.L", 0x31: "eyebrow.R.R",
            0x28: "eyebrow.L.R", 0x1F: "eyebrow.R"
        }

        def remove_empty_weights():
            nonlocal curr_bone_idx
            if len(curr_weights) == 0 and curr_bone_idx != 0:
                mesh_weights[curr_mesh].pop(curr_bone_idx)
                curr_bone_idx = 0
        
        def set_shape_pointer(armature, shape_obj):
            for mod in shape_obj.modifiers:
                if isinstance(mod, bpy.types.ArmatureModifier) and mod.object == armature:
                    return

            bpy.ops.object.select_all(action='DESELECT')
            select_object(shape_obj)

            bpy.ops.object.modifier_add(type='ARMATURE')
            shape_obj.modifiers[-1].show_expanded = False
            shape_obj.modifiers[-1].object = armature

        for command, params in dynlist:
            if (command == "MakeDynObj" and "D_NET" in params) or (command == "MakeNetWithSubGroup"):
                curr_object = bpy.data.objects.new(hex(params[1]), bpy.data.armatures.new("n64_net"))
                current_context.collection.objects.link(curr_object)
                select_object(curr_object)
                curr_object.show_in_front = True
                objects[hex(params[1])] = curr_object
                curr_armature = curr_object
                objects[params[1]] = curr_object
            
            elif command == "SetScale":
                if isinstance(curr_object, bpy.types.Object):
                    curr_object.scale = params

            elif command == "SetAttachOffset":
                offset = [num / 212.77 for num in params]
                if isinstance(curr_object, bpy.types.Object):
                    curr_object.location = offset
                elif isinstance(curr_object, bpy.types.EditBone):
                    curr_object.matrix = Matrix.Translation(offset) @ curr_object.matrix
            
            elif command == "SetRotation":
                if isinstance(curr_object, bpy.types.Object):
                    curr_object.rotation_euler = params
                elif isinstance(curr_object, bpy.types.EditBone):
                    curr_object.matrix = Euler([math.radians(rot) for rot in params]).to_matrix().to_4x4() @ curr_object.matrix
            
            elif command == "SetSkinShape":
                remove_empty_weights()
                mesh_weights.setdefault(params, {})
                curr_mesh = params

                obj_name = [k for k, v in obj_id_map.items() if v == params]
                if len(obj_name) == 0:
                    continue
                set_shape_pointer(curr_armature, objects[obj_name[0]])
            
            elif command == "AttachTo":
                if params[1] == 1001:
                    continue

                bpy.ops.object.select_all(action='DESELECT')
                if isinstance(curr_object, bpy.types.EditBone):
                    armature = bone_armature_map[curr_object]
                    select_object(armature)
                    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
                    curr_object.select = True
                    armature.data.edit_bones.active = curr_object
                    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
                else:
                    select_object(curr_object)
                
                other_obj = objects[params[1]]
                
                print("Attach %s to %s" % (curr_object, other_obj))
                
                if isinstance(other_obj, bpy.types.EditBone):
                    armature = bone_armature_map[other_obj]
                    select_object(armature)
                    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
                    other_obj.select = True
                    armature.data.edit_bones.active = other_obj
                    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
                    bpy.ops.object.parent_set(type='BONE')
                else:
                    select_object(other_obj)
                    bpy.ops.object.parent_set()
    
            elif command == "AttachNetToJoint":
                remove_empty_weights()
                curr_weights = mesh_weights[curr_mesh].setdefault(params[1], [])

                select_object(curr_armature)
                bpy.ops.object.mode_set(mode='EDIT', toggle=False)
                curr_bone_idx = params[1]
                curr_bone = curr_armature.data.edit_bones.new("bone")
                curr_bone.name = hex(params[1])
                curr_bone.head = (0.0, 0.0, 0.0)
                curr_bone.tail = (0.0, 0.5, 0.0)
                curr_bone.matrix = Matrix.Identity(4)
                bpy.ops.object.mode_set(mode='OBJECT')
                curr_object = curr_bone

                if params[1] in bone_id_map.keys():
                    curr_bone.name = bone_id_map[params[1]]

                print("Attach Net %s to Joint %s" % (curr_armature, curr_object))

                objects[params[1]] = curr_bone
                bone_armature_map[curr_bone] = curr_armature
            
            elif command == "SetSkinWeight":
                curr_weights.append((params[0], params[1] / 100.0))
        
        remove_empty_weights()
        
        for obj, id in obj_id_map.items():
            for name, weights in mesh_weights[id].items():
                vert_group = objects[obj].vertex_groups.new(name=bone_id_map[name])
                for index, weight in weights:
                    vert_group.add([index], weight, "REPLACE")


def execute(op, context):
    global current_context, vertex_count

    source_dir = bpy.path.abspath(context.scene.goddard.source_dir)
    goddard_file_path = os.path.join(source_dir, "src\\goddard\\dynlists\\")
    bpy.ops.object.select_all(action='DESELECT')
    current_context = context
    vertex_count = 0

    if not os.path.exists(source_dir):
        op.report({'ERROR'}, "The source directory does not exist!")
        return {'CANCELLED'}
    
    mario_objects = {
        "face": load_dynlist(
            os.path.join(goddard_file_path, "dynlist_mario_face.c"),
            "mario_Face_VtxData[VTX_NUM][3]",
            "mario_Face_FaceData[FACE_NUM][4]"
        ),
        "eyebrow.L": load_dynlist(
            os.path.join(goddard_file_path, "dynlists_mario_eyebrows_mustache.c"),
            "verts_mario_eyebrow_left[VTX_NUM][3]",
            "facedata_mario_eyebrow_left[FACE_NUM][4]"
        ),
        "eyebrow.R": load_dynlist(
            os.path.join(goddard_file_path, "dynlists_mario_eyebrows_mustache.c"),
            "verts_mario_eyebrow_right[VTX_NUM][3]",
            "facedata_mario_eyebrow_right[FACE_NUM][4]"
        ),
        "mustache": load_dynlist(
            os.path.join(goddard_file_path, "dynlists_mario_eyebrows_mustache.c"),
            "verts_mario_mustache[VTX_NUM][3]",
            "facedata_mario_mustache[FACE_NUM][4]"
        ),
        "eye.L": load_dynlist(
            os.path.join(goddard_file_path, "dynlists_mario_eyes.c"),
            "verts_mario_eye_left[VTX_NUM][3]",
            "facedata_mario_eye_left[FACE_NUM][4]"
        ),
        "eye.R": load_dynlist(
            os.path.join(goddard_file_path, "dynlists_mario_eyes.c"),
            "verts_mario_eye_right[VTX_NUM][3]",
            "facedata_mario_eye_right[FACE_NUM][4]"
        )
    }

    if None in mario_objects.items():
        op.report({'ERROR'}, "Dynlists could not be loaded!")
        return {'CANCELLED'}

    load_data_from_master_list(os.path.join(goddard_file_path, "dynlist_mario_master.c"), mario_objects)

    bpy.ops.object.select_all(action='DESELECT')
    for name, obj in mario_objects.items():
        if not isinstance(obj, bpy.types.Object):
            continue
        obj.name = hex(name) if isinstance(name, int) else str(name)

        if obj.parent == None:
            select_object(obj)

    # Mario's eye positions are generated by the game, so the following acts as a hardcoded placeholder.
    mario_objects["eye.L"].location = (0.31642, 0.737687, 0.032769)
    mario_objects["eye.L"].rotation_euler = (math.radians(45.3), math.radians(-85), math.radians(34.2))
    mario_objects["eye.R"].location = (-0.186127, 0.736151, 0.019117)
    mario_objects["eye.R"].rotation_euler = (math.radians(110), math.radians(-79.4), math.radians(161))

    head = bpy.data.objects.new("Mario Head", None)
    head.empty_display_type = "SPHERE"
    head.empty_display_size = 2.2
    context.collection.objects.link(head)
    select_object(head)
    bpy.ops.object.parent_set()
    head.rotation_euler = (math.radians(90.0), 0, 0)

    print(vertex_count)

    return {'FINISHED'}

