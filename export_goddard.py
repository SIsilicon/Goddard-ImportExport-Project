import bpy
import sys
import re

# The file path to the sm64 source repo
sm64_file_path = "C:/Path to sm64 src"

def load_dynlist(filepath):
    text = ""
    try:
        file = open(sm64_file_path + "/" + filepath)
        text = file.read()
        file.close()
    except:
        e = sys.exc_info()[0]
        print("Couldn't Load DynList(s) at'",filepath,"':", e)
    
    return text

def modify_dynlist(dynlist, object, vert_data_name, face_data_name, list_data_name):
    # get a triangulated version of the object's mesh 
    tri_mod = object.modifiers.new("triangulate", "TRIANGULATE")
    mesh = object.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
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
    dynlist = re.sub(
        list_data_name+r"\[(.+?)\]",
        list_data_name+"["+str(12+len(material_data))+"]",
        dynlist, 1
    )
    material_data = "\n    ".join(material_data)
    dynlist = re.sub(
        r"StartGroup\((.+?)\)(.*?)EndGroup",
        r"StartGroup(\1),\n    " + material_data + "\n    EndGroup",
        dynlist, 1, re.S
    )

    return dynlist

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

goddard_head = bpy.context.active_object
goddard_children = goddard_head.children

goddard_meshes = {}
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
    print("Some meshes are missing!")

dynlist_files = {
    "eyes": "src/goddard/dynlists/dynlists_mario_eyes.c",
    "eyebrows_mustache": "src/goddard/dynlists/dynlists_mario_eyebrows_mustache.c",
    "face": "src/goddard/dynlists/dynlist_mario_face.c"
}

# load and modify the dynlist file that the face will be saved in.
face_dynlist = load_dynlist(dynlist_files["face"])
face_dynlist = modify_dynlist(face_dynlist, goddard_meshes["face"], "mario_Face_VtxData", "mario_Face_FaceData", "dynlist_mario_face")

# load and modify the dynlist file that the eyes will be saved in.
eyes_dynlists = load_dynlist(dynlist_files["eyes"])
eyes_dynlists = split_dynlists(eyes_dynlists)

#print(eyes_dynlists[1])

eyes_dynlists[0] = modify_dynlist(eyes_dynlists[0], goddard_meshes["eye.R"], "verts_mario_eye_right", "facedata_mario_eye_right", "dynlist_mario_eye_right")
eyes_dynlists[1] = modify_dynlist(eyes_dynlists[1], goddard_meshes["eye.L"], "verts_mario_eye_left", "facedata_mario_eye_left", "dynlist_mario_eye_left")
eyes_dynlists = "\n".join(eyes_dynlists)

# load and modify the dynlist file that the eyebrows and mustache will be saved in.
brow_stache_dynlists = load_dynlist(dynlist_files["eyebrows_mustache"])
brow_stache_dynlists = split_dynlists(brow_stache_dynlists)

#print(brow_stache_dynlists[2])

brow_stache_dynlists[0] = modify_dynlist(brow_stache_dynlists[0], goddard_meshes["eyebrow.R"], "verts_mario_eyebrow_right", "facedata_mario_eyebrow_right", "dynlist_mario_eyebrow_right")
brow_stache_dynlists[1] = modify_dynlist(brow_stache_dynlists[1], goddard_meshes["eyebrow.L"], "verts_mario_eyebrow_left", "facedata_mario_eyebrow_left", "dynlist_mario_eyebrow_left")
brow_stache_dynlists[2] = modify_dynlist(brow_stache_dynlists[2], goddard_meshes["mustache"], "verts_mario_mustache", "facedata_mario_mustache", "dynlist_mario_mustache")
brow_stache_dynlists = "\n".join(brow_stache_dynlists)


src_head_file = open(sm64_file_path+"/src/goddard/dynlists/dynlists.h", "r")
header = src_head_file.read()
header = re.sub(r"(dynlist_mario_face)\[(.+?)\]", r"\1["+str(12+len(goddard_meshes["face"].material_slots)*4)+"]", header)

dest_head_file = open(sm64_file_path+"/dynlists.h", "w")
dest_head_file.write(header)

src_head_file.close()
dest_head_file.close()

file = open(sm64_file_path+"/dynlist_mario_face.c", "w")
if not "BLENDER" in face_dynlist:
    file.write("// MODIFIED BY A BLENDER ADDON //\n")
file.write(face_dynlist)
file.close()

file = open(sm64_file_path+"/dynlists_mario_eyes.c", "w")
if not "BLENDER" in eyes_dynlists:
    file.write("// MODIFIED BY A BLENDER ADDON //\n")
file.write(eyes_dynlists)
file.close()

file = open(sm64_file_path+"/dynlists_mario_eyebrows_mustache.c", "w")
if not "BLENDER" in brow_stache_dynlists:
    file.write("// MODIFIED BY A BLENDER ADDON //\n")
file.write(brow_stache_dynlists)
file.close()
