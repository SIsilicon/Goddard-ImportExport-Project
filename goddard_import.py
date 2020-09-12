import bpy
import ast
import os
import math
import sys

dir = os.path.dirname(bpy.data.filepath)
if not dir in sys.path:
    sys.path.append(dir )

import dynlist

import imp
imp.reload(dynlist)

D_MATERIAL = bpy.types.Material
D_LIGHT = bpy.types.Light
D_NET = bpy.types.Armature

current_mat = None
current_object = None

blend2sm64 = 212.77


def MakeDynObj(type, meta):
    global current_mat
    global current_object

    if type == D_MATERIAL:
        current_mat = bpy.data.materials.new(name = "n64_mat")
    elif type == D_LIGHT:
        current_mat = None
        current_object = bpy.data.objects.new("n64_light", bpy.data.lights.new(name = "Light", type = "POINT"))
        bpy.context.collection.objects.link(current_object)
        current_object.select_set(True)
        bpy.context.view_layer.objects.active = current_object
    elif type == D_NET:
        current_mat = None
        current_object = bpy.data.objects.new("n64_armature", bpy.data.armatures.new(name = "Armature"))
        bpy.context.collection.objects.link(current_object)
        current_object.select_set(True)
        bpy.context.view_layer.objects.active = current_object

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

def SetShapePtr(null_arg):
    pass

def SetScale(x, y, z):
    current_object.scale = (x, y, z)

def SetRotation(x, y, z):
    current_object.rotation_euler = (x, y, z)

def SetAttachOffset(x, y, z):
    current_object.location = (x / blend2sm64, y / blend2sm64, z / blend2sm64)

def SetAmbient(r, g, b):
    pass #print(["SetAmbient", r, g, b])

def SetDiffuse(r, g, b):
    if current_mat:
        current_mat.diffuse_color = (r, g, b, 1.0)
    else:
        current_object.color = (r, g, b, 1.0)

def SetFlag(null_arg):
    pass

def StartGroup(null_arg):
    pass

def SetType(null_arg):
    pass

def load_dynlist(filepath, vertex_data, face_data):
    file = open(filepath)
    obj = 0
    try:
        text = file.read()
        
        # Load vertices
        vertex_list = []
        arr_start1 = text.find(vertex_data + " = ")
        if arr_start1 != -1:
            arr_start1 += len(vertex_data + " = ")
            arr_end1 = text.find("};", arr_start1) + 1
            vertex_list = ast.literal_eval(text[arr_start1:arr_end1].replace("{", "[").replace("}", "]"))
            vertex_list = [val for sublist in vertex_list for val in sublist]
            for idx, _ in enumerate(vertex_list):
                vertex_list[idx] /= blend2sm64
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
            for idx, face in enumerate(face_list):
                face_list[idx] = face[1:4]
                mat_id_list.append(face[0])
            face_list = [val for sublist in face_list for val in sublist]
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
        mesh.polygons.foreach_set("loop_start", range(0, len(face_list)-1, 3))
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
        bpy.context.collection.objects.link(obj)

        obj.select_set(True)
        bpy.ops.object.shade_smooth()
        bpy.context.view_layer.objects.active = obj
    finally:
        file.close()
    
    return obj


goddard_file_path = "C:/Users/Student/Downloads/sm64pcbuilder2/Render96ex-master/src/goddard/dynlists/"
bpy.ops.object.select_all(action='DESELECT')

list = dynlist.DynListImport().LoadList(goddard_file_path + "dynlist_mario_master.c", "dynlist_mario_master")


#mario_objects = [
#    load_dynlist(
#        goddard_file_path + "dynlist_mario_face.c",
#        "mario_Face_VtxData[VTX_NUM][3]",
#        "mario_Face_FaceData[FACE_NUM][4]"
#    ),
#    load_dynlist(
#        goddard_file_path + "dynlists_mario_eyebrows_mustache.c",
#        "verts_mario_eyebrow_left[VTX_NUM][3]",
#        "facedata_mario_eyebrow_left[FACE_NUM][4]"
#    ),
#    load_dynlist(
#        goddard_file_path + "dynlists_mario_eyebrows_mustache.c",
#        "verts_mario_eyebrow_right[VTX_NUM][3]",
#        "facedata_mario_eyebrow_right[FACE_NUM][4]"
#    ),
#    load_dynlist(
#        goddard_file_path + "dynlists_mario_eyebrows_mustache.c",
#        "verts_mario_mustache[VTX_NUM][3]",
#        "facedata_mario_mustache[FACE_NUM][4]"
#    ),
#    load_dynlist(
#        goddard_file_path + "dynlists_mario_eyes.c",
#        "verts_mario_eye_left[VTX_NUM][3]",
#        "facedata_mario_eye_left[FACE_NUM][4]"
#    ),
#    load_dynlist(
#        goddard_file_path + "dynlists_mario_eyes.c",
#        "verts_mario_eye_right[VTX_NUM][3]",
#        "facedata_mario_eye_right[FACE_NUM][4]"
#    )
#]
#for idx, obj in enumerate(mario_objects):
#    obj.name = ["face", "eyebrow.L", "eyebrow.R", "mustache", "eye.L", "eye.R"][idx]


#head = bpy.data.objects.new("Mario Head", None)
#bpy.context.collection.objects.link(head)
#head.select_set(True)
#bpy.context.view_layer.objects.active = head
#bpy.ops.object.parent_set()