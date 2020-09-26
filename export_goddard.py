import bpy
import sys
import re
import ast
import os

# the file path to the sm64 source repo
sm64_source_dir = ""

# the vertex count of the default mario head
DEFAULT_VERTEX_COUNT = 644

# default params of the static display list in renderer.c
DEFAULT_MAX_GFX_IN_DL = 1900
DEFAULT_MAX_VERTS_IN_DL = 4000

# replacement code for goddard memory management
GD_MALLOC_SUB = """
    /*C MEM*/
    size = ALIGN(size, 8);
    sAllocMemory += size;
    return malloc(size);
    /*C MEM*/
"""
GD_FREE_SUB = """
    /*C MEM*/
    sAllocMemory -= sizeof(ptr);
    free(ptr);
    return;
    /*C MEM*/
"""

curr_context = None
total_vertex_count = 0
max_vertex_count_in_mesh = 0

def load_dynlist(filepath):
    text = ""
    with open(os.path.join(sm64_source_dir, filepath)) as file:
        text = file.read()
    return text

def modify_dynlist(dynlist, object, vert_data_name, face_data_name, list_data_name):
    global max_vertex_count_in_mesh, total_vertex_count
    
    # get a triangulated version of the object's mesh 
    tri_mod = object.modifiers.new("triangulate", "TRIANGULATE")
    mesh = object.evaluated_get(curr_context.evaluated_depsgraph_get()).to_mesh()
    object.modifiers.remove(tri_mod)

    # insert vertex data into file
    dynlist = re.sub(r"#define VTX_NUM (.*?)\n", "#define VTX_NUM " + str(len(mesh.vertices.values())) + " \n", dynlist, 1)
    vertex_data = []
    for vertex in mesh.vertices.values():
        vertex_data.append([
            int(vertex.co[0] * 212.77),
            int(vertex.co[1] * 212.77), 
            int(vertex.co[2] * 212.77)
        ])
    max_vertex_count_in_mesh = max(max_vertex_count_in_mesh, len(mesh.vertices.values()))
    total_vertex_count += len(mesh.vertices.values())
    vertex_data = str(vertex_data).replace("[", "{").replace("]", "}")
    dynlist = re.sub(
        vert_data_name+r"\[VTX_NUM\](.+?)};",
        vert_data_name+"[VTX_NUM][3] = " + vertex_data + ";",
        dynlist, 1, re.S
    )

    # insert face data into file
    dynlist = re.sub(r"#define FACE_NUM (.*?)\n", "#define FACE_NUM " + str(len(mesh.polygons.values())) + " \n", dynlist, 1)
    face_data = []
    for face in mesh.polygons.values():
        face_data.append([
            face.material_index,
            face.vertices[0],
            face.vertices[1],
            face.vertices[2]
        ])
    face_data = str(face_data).replace("[", "{").replace("]", "}")
    dynlist = re.sub(
        face_data_name+r"\[FACE_NUM\](.+?)};",
        face_data_name+"[FACE_NUM][4] = " + face_data + ";",
        dynlist, 1, re.S
    )
    
    # insert material data into file
    material_data = []
    for i, material_slot in enumerate(object.material_slots):
        material = material_slot.material
        material_data.append("MakeDynObj(D_MATERIAL, 0x0),")
        material_data.append("SetId("+str(i)+"),")
        
        color = material.diffuse_color
        color = (color[0], color[1], color[2])
        
        material_data.append("SetAmbient"+str(color)+",")
        material_data.append("SetDiffuse"+str(color)+",")

    list_length = 12 + len(material_data)

    dynlist = re.sub(
        list_data_name+r"\[(.+?)\]",
        list_data_name+"["+str(list_length)+"]",
        dynlist, 1
    )
    material_data = "\n    ".join(material_data)
    dynlist = re.sub(
        r"StartGroup\((.+?)\)(.*?)EndGroup",
        r"StartGroup(\1),\n    " + material_data + "\n    EndGroup",
        dynlist, 1, re.S
    )

    return dynlist, list_length

def modify_master_dynlist(dynlist, objects):
    original_list = dynlist[:]
    
    arr_start = dynlist.find("{")
    arr_end = dynlist.find("}") + 1
    dynlist = dynlist[arr_start:arr_end]

    dynlist = re.sub(r"//(.+?)\n", r"\n", dynlist, 0)
    dynlist = dynlist.replace("{", "[").replace("}", "]")
    dynlist = dynlist.replace("(", ", (").replace(" ", "")
    dynlist = re.sub(r"([a-wyzA-WYZ_\&][a-wyzA-WYZ_0-9]{3,100})", r"'\1'", dynlist, 0)
    dynlist = dynlist.replace(",\n", "],\n").replace("\n'", "\n['")
    dynlist = ast.literal_eval(dynlist)
    
    weight_id_map = {
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
    obj_id_map = {
        0xE1: "face", 0x3B: "eyebrow.L",
        0x5D: "eyebrow.R", 0x19: "mustache"
    }
    
    i = 0
    current_object = None
    object_weights = {}
    current_vert_group = None
    weight_begin, weight_end = -1, -1
    while i < len(dynlist):
        command, params = dynlist[i]
        
        if command != "SetSkinWeight" and weight_begin != -1:
            del dynlist[weight_begin:weight_end]
            
            print(current_object.name, len(current_object.data.vertices))
            weight_end = weight_begin
            sublist = []
            vert_group_index = current_vert_group.index
            
            for j, vert in enumerate(current_object.data.vertices):
                for grp in vert.groups:
                    if grp.group == vert_group_index and grp.weight != 0.0: 
                        sublist.append(["SetSkinWeight", (j, round(grp.weight * 100.0, 3))])
                        weight_end += 1
            dynlist[weight_begin:weight_begin] = sublist
            
            i = weight_end + 1
            weight_begin = -1
            continue

        if command == "SetSkinShape":
            if current_object:
                bpy.ops.object.select_all(action="DESELECT")
                current_object.select_set(True)
                curr_context.view_layer.objects.active = current_object
                bpy.ops.object.delete()

            # use a version of the mesh with its modifiers applied
            bpy.ops.object.select_all(action="DESELECT")
            objects[obj_id_map[params]].select_set(True)
            curr_context.view_layer.objects.active = objects[obj_id_map[params]]
            bpy.ops.object.duplicate()
            bpy.ops.object.modifier_add(type="TRIANGULATE")
            current_object = curr_context.view_layer.objects.active
            for mod in current_object.modifiers:
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except RuntimeError:
                    bpy.ops.object.modifier_remove(modifier=mod.name)
            
            for vert_group in current_object.vertex_groups:
                object_weights[vert_group.name] = vert_group
        elif command == "AttachNetToJoint":
            if params[1] in weight_id_map:
                current_vert_group = object_weights[weight_id_map[params[1]]]
            else:
                current_vert_group = None
        if command == "SetSkinWeight":
            if weight_begin == -1:
                weight_begin = i
            else:
                weight_end = i
        i+=1
    
    if current_object:
        bpy.ops.object.select_all(action="DESELECT")
        current_object.select_set(True)
        curr_context.view_layer.objects.active = current_object
        bpy.ops.object.delete()
    bpy.ops.outliner.orphans_purge()
    
    list_string = "dynlist_mario_master["+str(len(dynlist))+"] = {\n"
    for command, params in dynlist:
        param_string = str(params).replace("'", "")
        if not type(params) is tuple:
            param_string = "(" + param_string + ")"
        
        list_string += "    " + command + param_string + ",\n"
    list_string += "};"
    
    list_string = re.sub(r"dynlist_mario_master\[(.+)};", list_string, original_list, 1, re.S)
    
    return list_string, len(dynlist)

def split_dynlists(dynlist):
    lists = []
    
    splitpoint = "#define VTX_NUM"
    first_iteration = True
    offset = 0
    while len(dynlist) != 0:
        offset = dynlist.find(splitpoint, 1)
        
        if offset == -1:
            if first_iteration:
                print("Invalid dynlist! Can't split.")
                return
            else:
                lists.append(dynlist)
                break

        if offset != -1:
            if first_iteration:
                offset = dynlist.find(splitpoint, offset + 1)
                if offset == -1:
                    return dynlist
                else:
                    lists.append(dynlist[:offset])
                    dynlist = dynlist[offset:]
            else:
                lists.append(dynlist[:offset])
                dynlist = dynlist[offset:]
        
        first_iteration = False
    
    return lists

def exceute(op, context):
    global curr_context, sm64_source_dir, total_vertex_count, max_vertex_count_in_mesh
    
    total_vertex_count = 0
    max_vertex_count_in_mesh = 0
    curr_context = context
    goddard_head = context.active_object

    if not goddard_head:
        op.report({'ERROR'}, "A goddard head is not selected!")
        return {'CANCELLED'}

    # Get goddard meshes
    goddard_children = goddard_head.children
    goddard_meshes = {}
    mesh_names = ["eye.L", "eye.R", "eyebrow.L", "eyebrow.R", "face", "mustache"]
    for mesh in goddard_children:
        if "eye.L" in mesh.name:
            goddard_meshes["eye.L"] = mesh
        elif "eye.R" in mesh.name:
            goddard_meshes["eye.R"] = mesh
        elif "eyebrow.L" in mesh.name:
            goddard_meshes["eyebrow.L"] = mesh
        elif "eyebrow.R" in mesh.name:
            goddard_meshes["eyebrow.R"] = mesh
        elif "face" in mesh.name:
            goddard_meshes["face"] = mesh
        elif "mustache" in mesh.name:
            goddard_meshes["mustache"] = mesh

    if len(goddard_meshes.items()) != 6:
        missing_meshes = [name for name in mesh_names if not name in goddard_meshes.keys()]
        op.report({'ERROR'}, "The selected object does not have the following mesh children: %s" %\
            str(missing_meshes)
        )
        return {'CANCELLED'}

    sm64_source_dir = bpy.path.abspath(context.scene.goddard.source_dir)
    dynlist_files = {
        "eyes": "src/goddard/dynlists/dynlists_mario_eyes.c",
        "eyebrows_mustache": "src/goddard/dynlists/dynlists_mario_eyebrows_mustache.c",
        "face": "src/goddard/dynlists/dynlist_mario_face.c",
        "master": "src/goddard/dynlists/dynlist_mario_master.c"
    }

    if not os.path.exists(sm64_source_dir):
        op.report({'ERROR'}, "The source directory does not exist!")
        return {'CANCELLED'}

    # load and modify the master dynlist file
    master_dynlist = load_dynlist(dynlist_files["master"])
    master_dynlist, master_size = modify_master_dynlist(master_dynlist, goddard_meshes)

    # load and modify the dynlist file that the face will be saved in.
    face_dynlist = load_dynlist(dynlist_files["face"])
    face_dynlist, face_size = modify_dynlist(face_dynlist, goddard_meshes["face"], "mario_Face_VtxData", "mario_Face_FaceData", "dynlist_mario_face")

    # load and modify the dynlist file that the eyes will be saved in.
    eyes_dynlists = load_dynlist(dynlist_files["eyes"])
    eyes_dynlists = split_dynlists(eyes_dynlists)

    eyes_dynlists[0], eye_size_r = modify_dynlist(eyes_dynlists[0], goddard_meshes["eye.R"], "verts_mario_eye_right", "facedata_mario_eye_right", "dynlist_mario_eye_right")
    eyes_dynlists[1], eye_size_l = modify_dynlist(eyes_dynlists[1], goddard_meshes["eye.L"], "verts_mario_eye_left", "facedata_mario_eye_left", "dynlist_mario_eye_left")
    eyes_dynlists = "\n".join(eyes_dynlists)

    # load and modify the dynlist file that the eyebrows and mustache will be saved in.
    brow_stache_dynlists = load_dynlist(dynlist_files["eyebrows_mustache"])
    brow_stache_dynlists = split_dynlists(brow_stache_dynlists)

    brow_stache_dynlists[0], eyebrow_size_r = modify_dynlist(brow_stache_dynlists[0], goddard_meshes["eyebrow.R"], "verts_mario_eyebrow_right", "facedata_mario_eyebrow_right", "dynlist_mario_eyebrow_right")
    brow_stache_dynlists[1], eyebrow_size_l = modify_dynlist(brow_stache_dynlists[1], goddard_meshes["eyebrow.L"], "verts_mario_eyebrow_left", "facedata_mario_eyebrow_left", "dynlist_mario_eyebrow_left")
    brow_stache_dynlists[2], mustache_size = modify_dynlist(brow_stache_dynlists[2], goddard_meshes["mustache"], "verts_mario_mustache", "facedata_mario_mustache", "dynlist_mario_mustache")
    brow_stache_dynlists = "\n".join(brow_stache_dynlists)

    os.makedirs(sm64_source_dir + "/goddard/dynlists/", exist_ok=True)

    # write the dynlist lengths into the dynlists header file.
    with open(sm64_source_dir+"/src/goddard/dynlists/dynlists.h", "r") as src_head_file:
        header = src_head_file.read()
        header = re.sub(r"(dynlist_mario_master)\[(.+?)\]", r"\1["+str(master_size)+"]", header)
        header = re.sub(r"(dynlist_mario_face)\[(.+?)\]", r"\1["+str(face_size)+"]", header)
        header = re.sub(r"(dynlists_mario_eye_right)\[(.+?)\]", r"\1["+str(eye_size_r)+"]", header)
        header = re.sub(r"(dynlists_mario_eye_left)\[(.+?)\]", r"\1["+str(eye_size_l)+"]", header)
        header = re.sub(r"(dynlists_mario_eyebrow_right)\[(.+?)\]", r"\1["+str(eyebrow_size_r)+"]", header)
        header = re.sub(r"(dynlists_mario_eyebrow_left)\[(.+?)\]", r"\1["+str(eyebrow_size_l)+"]", header)
        header = re.sub(r"(dynlists_mario_mustache)\[(.+?)\]", r"\1["+str(mustache_size)+"]", header)

        with open(sm64_source_dir+"/goddard/dynlists/dynlists.h", "w") as dest_head_file:
            dest_head_file.write(header)

    # write the dynlists into their respective files.
    with open(sm64_source_dir+"/goddard/dynlists/dynlist_mario_master.c", 'w') as file:
        if not "BLENDER" in face_dynlist:
            file.write("// MODIFIED BY A BLENDER ADDON //\n")
        file.write(master_dynlist)

    with open(sm64_source_dir+"/goddard/dynlists/dynlist_mario_face.c", "w") as file:
        if not "BLENDER" in face_dynlist:
            file.write("// MODIFIED BY A BLENDER ADDON //\n")
        file.write(face_dynlist)

    with open(sm64_source_dir+"/goddard/dynlists/dynlists_mario_eyes.c", "w") as file:
        if not "BLENDER" in eyes_dynlists:
            file.write("// MODIFIED BY A BLENDER ADDON //\n")
        file.write(eyes_dynlists)

    with open(sm64_source_dir+"/goddard/dynlists/dynlists_mario_eyebrows_mustache.c", "w") as file:
        if not "BLENDER" in brow_stache_dynlists:
            file.write("// MODIFIED BY A BLENDER ADDON //\n")
        file.write(brow_stache_dynlists)
    
    # prepend the gd_malloc and gd_free functions with stdlib malloc and free respectively.
    with open(sm64_source_dir + "/src/goddard/renderer.c", 'r') as src_file:
        code = src_file.read()
        
        if context.scene.goddard.c_memory_management:
            if code.find("<stdlib.h>") == -1:
                code = "#include <stdlib.h>\n" + code
            if code.find(GD_MALLOC_SUB) == -1:
                code = re.sub(r"(\*gd_malloc\((.*?){)",r"\1" + GD_MALLOC_SUB, code, 1, re.S)
            if code.find(GD_FREE_SUB) == -1:
                code = re.sub(r"(gd_free\((.*?){)",r"\1" + GD_FREE_SUB, code, 1, re.S)
        else:
            code = code.replace("#include <stdlib.h>\n", "")
            code = code.replace(GD_MALLOC_SUB, "")
            code = code.replace(GD_FREE_SUB, "")

        ratio = total_vertex_count / DEFAULT_VERTEX_COUNT
        code = re.sub(r"(sStaticDl = new_gd_dl\(0,)(.*?),(.*?),",
            r"\1 %d, %d," % (DEFAULT_MAX_GFX_IN_DL * ratio, DEFAULT_MAX_VERTS_IN_DL * ratio),
            code, 1, re.S
        )
    
        with open(sm64_source_dir + "/goddard/renderer.c", 'w') as dst_file:
            dst_file.write(code)

    # adjust maximum vertex count in dynlist_proc.c
    with open(sm64_source_dir + "/src/goddard/dynlist_proc.c", 'r') as src_file:
        code = src_file.read()
        code = re.sub(r"(#define VTX_BUF_SIZE)(.*?)\n", r"\1 %d\n" % (max(max_vertex_count_in_mesh * 1.5, 3000.0)), code, 1, re.S)

        with open(sm64_source_dir + "/goddard/dynlist_proc.c", 'w') as dst_file:
            dst_file.write(code)

    return {'FINISHED'}
