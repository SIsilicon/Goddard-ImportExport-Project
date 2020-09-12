import bpy
import sys
import ast
import os
import math
import copy
import re

dir = os.path.dirname(bpy.data.filepath)
if not dir in sys.path:
    sys.path.append(dir)
import dynlist_classes
import gd_math
from dynlist_classes import *
from gd_math import *

import imp
imp.reload(dynlist_classes)
imp.reload(gd_math)

DYNOBJ_NAME_SIZE = 8
DYNOBJ_LIST_SIZE = 3000
VTX_BUF_SIZE = 3000

# types
#/ Information about a dynamically created `GdObj`
class DynObjInfo:
    def __init__(self):
        self.name = ""
        self.obj = None
        self.num = 0
#   unk

##/ @name DynList Accessors
##/ Accessor marcos for easy interpretation of data in a `DynList` packet
##/@[
Dyn1AsInt = lambda dyn : dyn.w1.word
Dyn1AsPtr = lambda dyn : dyn.w1.ptr
Dyn1AsStr = lambda dyn : dyn.w1.str
Dyn1AsID = lambda dyn : dyn.w1.ptr

Dyn2AsInt = lambda dyn : dyn.w2.word
Dyn2AsPtr = lambda dyn : dyn.w2.ptr
Dyn2AsStr = lambda dyn : dyn.w2.str
Dyn2AsID = lambda dyn : dyn.w2.ptr

DynVec = lambda dyn : dyn.vec
DynVecX = lambda dyn : dyn.vec.x
DynVecY = lambda dyn : dyn.vec.y
DynVecZ = lambda dyn : dyn.vec.z

DynIdAsStr = lambda id : str(id)
DynIdAsInt = lambda id : int(id)
AsDynId = lambda unk : unk

##/@]

## data
sGdDynObjList = None # @ 801A8250 info for all loaded/made dynobjs
sDynListCurObj = None # @ 801A8254
sGdNullPlaneF = [        # @ 801A8258
    [ 0.0, 0.0, 0.0 ],
    [ 0.0, 0.0, 0.0 ]
]
sGdDynObjIdIsInt = False # @ 801A8270 str (0) or int (1) for Dyn Obj ID

## bss
sIntDynIdBuffer = "" #/< buffer for returning formated string from
#                                               #/< `print_int_dynid()`
sNullDynObjInfo = None      # @ 801B9F08
sDynIdBuf = ""       # @ 801B9F20 small buf for printing dynid to?
sUnnamedObjCount = 0    # @ 801B9F28 used to print empty string ids (not None char *) to sDynIdBuf
sLoadedDynObjs = 0
sDynListCurInfo = None # @ 801B9F30 info for most recently added object
ParentNetInfo = None #/< Information for `ObjNet` made by `d_add_net_with_subgroup()`
sStashedDynObjInfo = None # @ 801B9F38
sStashedDynObj = None     # @ 801B9F3C
sDynNetCount = 0          # @ 801B9F40
sDynNetIdBuf = ""               # @ 801B9F48
sBackBuf = ""                  # @ 801B9F68

gGdGroupList = None  # @ 801B9E54
gGdObjCount = 0      # @ 801B9E58
gGdGroupCount = 0    # @ 801B9E5C
gGdPlaneCount = 0    # @ 801B9E60
gGdCameraCount = 0   # @ 801B9E64
gGdJointList = None  # @ 801B9E84
gGdBoneList = None   # @ 801B9E88
gGdObjectList = None # @ 801B9E8C
gGdViewsGroup = None # @ 801B9E90
gGdLightGroup = None
gGdSkinNet = None
sGdShapeCount = 0 

sGdShapeListHead = None

def apply_to_obj_types_in_group(types, fn, group):
    fnAppliedCount = 0

    if group == None:
        return fnAppliedCount

    if group.linkType & 1: # compressed data, not an Obj
        return fnAppliedCount
 
    if not((group.groupObjTypes & ObjTypeFlag.OBJ_TYPE_GROUPS.value) | (group.groupObjTypes & types)):
        return fnAppliedCount

    objFn = fn
    curLink = group.link1C

    while curLink != None:
        linkedObj = curLink.obj
        linkedObjType = linkedObj.type
        nextLink = curLink.next

        if linkedObjType == ObjTypeFlag.OBJ_TYPE_GROUPS:
            fnAppliedCount += apply_to_obj_types_in_group(types, fn, linkedObj)
        
        if linkedObjType & types:
            objFn(linkedObj)
            fnAppliedCount += 1
        
        curLink = nextLink
    
    return fnAppliedCount

def make_group(count, *args):
    global gGdGroupCount, gGdGroupList
    
    newGroup = make_object(ObjTypeFlag.OBJ_TYPE_GROUPS.value)
    newGroup.__class__ = ObjGroup
    gGdGroupCount += 1
    newGroup.id = gGdGroupCount
    newGroup.objCount = 0
    newGroup.link1C = newGroup.link20 = None

    print("Made group no.",newGroup.id,"\n")

    oldGroupListHead = gGdGroupList
    gGdGroupList = newGroup
    if (oldGroupListHead != None):
        newGroup.next = oldGroupListHead
        oldGroupListHead.prev = newGroup

    if (count == 0):
        return newGroup

    curLink = None
    for vargObj in args:
        curObj = vargObj
        newGroup.groupObjTypes |= curObj.type
        addto_group(newGroup, vargObj)

    curLink = newGroup.link1C
    print("Made group no.",newGroup.id," from: ")
    while curLink != None:
        curObj = curLink.obj
        curLink = curLink.next
   
    return newGroup

def make_group_of_type(type, fromObj, toObj):
    newGroup = make_group(0)
    curObj = fromObj

    while curObj != None:
        if curObj.type & type:
            addto_group(newGroup, curObj)
       
        if curObj == toObj:
            break

        curObj = curObj.prev

    return newGroup

def make_light(flags, name, id):
    newLight = make_object(ObjTypeFlag.OBJ_TYPE_LIGHTS.value)
    newLight.__class__ = ObjLight

    newLight.name = name if name != None else "NoName"
    
    newLight.id = id
    newLight.unk30 = 1.0
    newLight.unk4C = 0
    newLight.flags = flags | GdLightFlags.LIGHT_NEW_UNCOUNTED.value
    newLight.unk98 = 0
    newLight.unk40 = 0
    newLight.unk68.x = newLight.unk68.y = newLight.unk68.z = 0

    return newLight

def reset_net(net):
    net.unk14.x = net.unk20.x
    net.unk14.y = net.unk20.y
    net.unk14.z = net.unk20.z
    net.unk50.x = net.unk50.y = net.unk50.z = 0.0
    net.unkA4.x = net.unkA4.y = net.unkA4.z = 0.0

#    func_80191F10(net)

    gGdSkinNet = net
#    D_801BAAF4 = 0
    net.mat168 = get_identity_matrix()
    net.matE8 = get_identity_matrix()
    gd_rot_mat_about_vec(net.matE8, net.unk68) # set rot mtx to initial rotation?
   
    print(net.matE8, net.unk14)
    gd_add_vec3f_to_mat4f_offset(net.matE8, net.unk14) # set to initial position?
    net.mat128 = net.matE8

    grp = net.unk1C8
    # TODO
#    if grp != None:
#        def func_80191220(j):
#            j.unk48.x = j.unk54.x # storing "attached offset"?
#            j.unk48.y = j.unk54.y
#            j.unk48.z = j.unk54.z

#            gd_mat4f_mult_vec3f(j.unk48, gGdSkinNet.mat128)
#            j.unk3C.x = j.unk48.x
#            j.unk3C.y = j.unk48.y
#            j.unk3C.z = j.unk48.z
#            j.unk14.x = gGdSkinNet.unk14.x
#            j.unk14.y = gGdSkinNet.unk14.y
#            j.unk14.z = gGdSkinNet.unk14.z

#            j.unk14.x += j.unk3C.x
#            j.unk14.y += j.unk3C.y
#            j.unk14.z += j.unk3C.z
#            j.unk1A8.x = j.unk1A8.y = j.unk1A8.z = 0.0

#        apply_to_obj_types_in_group(ObjTypeFlag.OBJ_TYPE_JOINTS, func_80191604, grp)
#        apply_to_obj_types_in_group(ObjTypeFlag.OBJ_TYPE_JOINTS, func_80191220, grp)
#        apply_to_obj_types_in_group(ObjTypeFlag.OBJ_TYPE_BONES, func_8018FB58, grp)
#        apply_to_obj_types_in_group(ObjTypeFlag.OBJ_TYPE_BONES, func_8018FA68, grp)

def make_net(a0, shapedata, a2, a3, a4):
    net = make_object(ObjTypeFlag.OBJ_TYPE_NETS.value)
    net.__class__ = ObjNet
    print(vars(ObjNet))
    net.mat128 = get_identity_matrix()
    net.unk20.x = net.unk20.y = net.unk20.z = 0.0
#    net.unk38 = ++sNetCount
    net.unk1AC.x = net.unk1AC.y = net.unk1AC.z = 1.0
    net.unk1A8 = shapedata
    net.unk1C8 = a2
    net.unk1CC = a3
    net.unk1D0 = a4
    net.netType = 0
    net.unk210 = 0
    net.unk21C = None
    net.unk3C = 1
    net.unk40 = 0
    net.skinGrp = None
    reset_net(net)

    return net

def make_material(a0, name, id):
    newMtl = make_object(ObjTypeFlag.OBJ_TYPE_MATERIALS.value)
    newMtl.__class__ = ObjMaterial

    if name != None:
        newMtl.name = name
    else:
        newMtl.name, "NoName"

    newMtl.id = id
    newMtl.gddlNumber = 0
    newMtl.type = 16

    return newMtl

def make_shape(flag, name):
    global sGdShapeCount, sGdShapeListHead

    newShape = make_object(ObjTypeFlag.OBJ_TYPE_SHAPES.value)
    newShape.__class__ = ObjShape

    if name != None:
        newShape.name = name
    else:
        newShape.name = "NoName"
    

    sGdShapeCount += 1

    curShapeHead = sGdShapeListHead
    sGdShapeListHead = newShape

    if curShapeHead != None:
        newShape.nextShape = curShapeHead
        curShapeHead.prevShape = newShape

    newShape.id = sGdShapeCount
    newShape.flag = flag

    newShape.vtxCount = 0
    newShape.faceCount = 0
    newShape.gdDls[0] = 0
    newShape.gdDls[1] = 0
    newShape.unk3C = 0
    newShape.faceGroup = None # whoops, None-ed twice

    newShape.unk58 = 1.0

    newShape.vtxGroup = None
    newShape.faceGroup = None
    newShape.mtlGroup = None
    newShape.unk30 = 0
    newShape.gdDls[2] = 0

    return newShape

def addto_group(group, obj):
    if group.link1C == None:
        group.link1C = make_link_to_obj(None, obj)
        group.link20 = group.link1C
    else:
        group.link20 = make_link_to_obj(group.link20, obj)

    group.groupObjTypes |= obj.type
    group.objCount += 1

def make_link_to_obj(head, a1):
    newLink = Links()

    if head != None:
        head.next = newLink

    newLink.prev = head
    newLink.next = None
    newLink.obj = a1

    return newLink

def make_object(objType):
    global gGdObjCount
    global gGdObjectList

    newObj = GdObj()
    gGdObjCount += 1
    objListOldHead = gGdObjectList
    gGdObjectList = newObj

    newObj.prev = None
    if objListOldHead != None:
        newObj.next = objListOldHead
        objListOldHead.prev = newObj

    newObj.number = gGdObjCount
    newObj.type = objType
    newObj.objDrawFn = None
    newObj.drawFlags = 0

    return newObj

## Forward Declaration Here

"""*
 * Store the active dynamic `GdObj` into a one object stash.
 """
def push_dynobj_stash():
    global sStashedDynObjInfo, sStashedDynObj
    sStashedDynObjInfo = sDynListCurInfo
    sStashedDynObj = sDynListCurObj

"""*
 * Set the stashed `GdObj` as the active dynamic `GdObj`.
 """
def pop_dynobj_stash():
    global sDynListCurInfo, sDynListCurObj
    sDynListCurObj = sStashedDynObj
    sDynListCurInfo = sStashedDynObjInfo

"""*
 * Reset dynlist related variables to a starting state
 """
def reset_dynlist():
    sUnnamedObjCount = 0
    sLoadedDynObjs = 0
    sDynIdBuf = '\0'
    sGdDynObjList = None
    sDynListCurObj = None
    sDynNetCount = 0
    sGdDynObjIdIsInt = False
    sNullDynObjInfo.name = "NullObj"


"""*
 * Copy input `str` into a buffer that will be concatenated to a dynamic
 * `GdObj`'s name string when creating a new dynamic object. If input
 * is `None`, then a generic string is created based on the number of
 * unnamed objects.
 """
def d_copystr_to_idbuf(stri):
    global sDynIdBuf, sUnnamedObjCount
    
    if stri != None:
        if stri == "":
            sUnnamedObjCount += 1
            print(str(sDynIdBuf)+"__"+str(sUnnamedObjCount))
        else:
            sDynIdBuf = stri
    else:
        sDynIdBuf = ""

#"""*
# * Concatenate input `str` into a buffer that will be concatenated to a dynamic
# * `GdObj`'s name string when creating a new dynamic object. If input
# * is `None`, then a generic string is created based on the number of
# * unnamed objects.
# *
# * @note Not called
# """
#def d_catstr_to_idbuf(str):
#    char buf[0xff + 1]

#    if str != None):
#        if str[0] == '\0'):
#            sprint(buf, "__%d", ++sUnnamedObjCount)
#        else:
#            gd_strcpy(buf, str)
#        ]
#    else:
#        buf[0] = '\0'
#

#    gd_strcat(sDynIdBuf, buf)
#

"""*
 * Stash the current string that is appended to a created dynamic `GdObj` name.
 """
def cpy_idbuf_to_backbuf():
    global sBackBuf
    sBackBuf = sDynIdBuf

"""*
 * Pop the stash for the string that is appended to a created dynamic `GdObj` name.
 """
def cpy_backbuf_to_idbuf():
    global sDynIdBuf
    sDynIdBuf = sBackBuf

"""*
 * Get the `DynObjInfo` class for object `id`
 *
 * @param id Either a string or integer id for a dynamic `GdObj`
 * @returns pointer to that object's information
 """
def get_dynobj_info(id):
    buf = ""

    if sLoadedDynObjs == 0:
        return None

    if sGdDynObjIdIsInt:
        print(buf, "N%d", DynIdAsInt(id))
    else:
        buf = DynIdAsStr(id) # strcpy

    buf += sDynIdBuf # strcat
    foundDynobj = None
    print("Printing")
    for i in range(sLoadedDynObjs):
        print(sGdDynObjList[i].name, ": ", i)
        if sGdDynObjList[i].name == buf: # strcmp equal
            foundDynobj = sGdDynObjList[i]
            break

    return foundDynobj


#"""*
# * Reset the number of created dynamic objects and
# * free the dynamic object information list (`sGdDynObjList`).
# * The objects themselves still exist, though.
# *
# * @note Not called
# """
#def reset_dynamic_objs(def):
#    UNUSED s32 pad

#    if sLoadedDynObjs == 0):
#        return
#

#    gd_free(sGdDynObjList)
#    sLoadedDynObjs = 0
#    sGdDynObjList = None
#

"""*
 * Create an `ObjNet` and an associated node `ObjGroup`. This function creates
 * its own naming string to append to later created dynamic objects.
 """
def d_add_net_with_subgroup(a0, id):
    global sParentNetInfo, sDynNetCount
    
    d_makeobj(DObjTypes.D_NET.value, id)
    d_set_obj_draw_flag(ObjDrawingFlags.OBJ_NOT_DRAWABLE.value)
    # this creates a string to append to the names of the objs created after this
    sDynNetCount += 1
    print(sDynNetIdBuf, "c%d", sDynNetCount)
    d_set_type(4)
    cpy_idbuf_to_backbuf()
    d_copystr_to_idbuf(sDynNetIdBuf)
    d_start_group(id)
    cpy_backbuf_to_idbuf()
    d_use_obj(id)
    sParentNetInfo = sDynListCurInfo

"""*
 * End the `ObjNet`+`ObjGroup` set created by `d_add_net_with_subgroup()`.
 """
def d_end_net_subgroup(id):
    d_use_obj(id)
    cpy_idbuf_to_backbuf()
    d_copystr_to_idbuf(sDynNetIdBuf)
    d_end_group(id)
    d_set_nodegroup(id)
    cpy_backbuf_to_idbuf()
    sParentNetInfo = None


"""*
 * Create an `ObjJoint` and add that to the `ObjNet` created by
 * `d_add_net_with_subgroup()`.
 *
 * @param arg0 Not used
 * @param id   Id for created `ObjJoint`
 """
def d_attach_joint_to_net(arg0, id):
    d_makeobj(DObjTypes.D_JOINT.value, id)
    d_set_type(3)
    d_set_shapeptrptr(None)
    d_attach_to(0xD, sParentNetInfo.obj)
    sParentNetInfo = sDynListCurInfo

"""*
 * Create a new `ObjNet` linked with the dynamic `ObjShape` `id`.
 * The newly made net is added to the dynamic object list.
 """
def d_make_netfromshapeid(id):
    dyninfo = get_dynobj_info(id)
    
    if dyninfo == None:
        print("dMakeNetFromShape(",DynIdAsStr(id),"): Undefined object")

    net = make_netfromshape(dyninfo.obj)
    add_to_dynobj_list(net, None)


"""*
 * Create a new `ObjNet` linked with the doubly indirected `ObjShape`.
 * The newly made net is added to the dynamic object list, but
 * the shape is not moved into the dynamic list.
 """
def d_make_netfromshape_ptrptr(shapePtr):
    net = make_netfromshape(shapePtr)
    print("dMakeNetFromShapePtrPtr\n")
    add_to_dynobj_list(net, None)


"""*
 * Add `newobj` identified by `id` to the dynamic `GdObj` list. Once a `GdObj`
 * is in the dynamic list, it can referred to by its `id` when that object is
 * needed later.
 """
def add_to_dynobj_list(newobj, id):
    global sGdDynObjList, sLoadedDynObjs, sDynListCurObj, sDynListCurInfo
    idbuf = ""
    
    print("NEWOBJ: ", newobj)

#    start_memtracker("dynlist")
    
    if sGdDynObjList == None:
        sGdDynObjList = [GdObj()] * DYNOBJ_LIST_SIZE

#    stop_memtracker("dynlist")

    if sGdDynObjIdIsInt:
        print(idbuf, "N%d", DynIdAsInt(id))
        id = None
    else:
        print(idbuf, "U%d", sLoadedDynObjs + 1)

    sGdDynObjList[sLoadedDynObjs] = newobj
    if DynIdAsStr(id) != None:
        if get_dynobj_info(id) != None:
            print("WARNING")
            print("dMakeObj(",DynIdAsStr(id),"): Object with same name already exists")
        sGdDynObjList[sLoadedDynObjs].name = DynIdAsStr(id)
    else:
        sGdDynObjList[sLoadedDynObjs].name = idbuf

    sGdDynObjList[sLoadedDynObjs].name += sDynIdBuf
    print("NAME: ", sGdDynObjList[sLoadedDynObjs].name)

    if len(sGdDynObjList[sLoadedDynObjs].name) > (DYNOBJ_NAME_SIZE - 1):
        print("dyn list obj name too long ", sGdDynObjList[sLoadedDynObjs].name)
    
    sGdDynObjList[sLoadedDynObjs].num = sLoadedDynObjs
    sDynListCurInfo = sGdDynObjList[sLoadedDynObjs]
    sGdDynObjList[sLoadedDynObjs].obj = newobj
    sLoadedDynObjs += 1

    # A good place to bounds-check your array is
    # after you finish writing a new member to it.
    if sLoadedDynObjs >= DYNOBJ_LIST_SIZE:
        print("dMakeObj(): Too many dynlist objects")

    sDynListCurObj = newobj


"""*
 * Format `id` into string, if `DynId`s are currently being interpreted
 * as numbers.
 *
 * @returns pointer to global buffer for id
 * @retval None if `id` is `None` or if `DynId`s are interpreted as strings
 """
def print_int_dynid(id):
    if id and sGdDynObjIdIsInt:
        print(sIntDynIdBuffer, "N%d", DynIdAsInt(id))
        return sIntDynIdBuffer

    return None


"""*
 * Create a new `GdObj` of `type` and add that object to the
 * dynamic object list with `id`. Created objects have else
 * parameters, which are usually 0 or None.
 *
 * @returns pointer to created object
 """
def d_makeobj(type, id):
    dobj = None
    
    if type == DObjTypes.D_CAR_DYNAMICS.value:
        print("dmakeobj() Car dynamics are missing!")
    elif type == DObjTypes.D_JOINT.value:
        dobj = make_joint(0, 0.0, 0.0, 0.0)
    elif type == DObjTypes.D_ANOTHER_JOINT.value:
        dobj = make_joint(0, 0.0, 0.0, 0.0)
    elif type == DObjTypes.D_NET.value:
        dobj = make_net(0, None, None, None, None)
    elif type == DObjTypes.D_GROUP.value:
        dobj = make_group(0)
    elif type == DObjTypes.D_DATA_GRP.value:
        d_makeobj(DObjTypes.D_GROUP.value, id)
        sDynListCurObj.linkType = 1
        return None
    elif type == DObjTypes.D_CAMERA.value:
        dobj = make_camera(0, None)
    elif type == DObjTypes.D_BONE.value:
        dobj = make_bone(0, None, None, 0)
    elif type == DObjTypes.D_PARTICLE.value:
        dobj = make_particle(0, 0, 0.0, 0.0, 0.0)
    elif type == DObjTypes.D_VERTEX.value:
        dobj = gd_make_vertex(0.0, 0.0, 0.0)
    elif type == DObjTypes.D_FACE.value:
        dobj = make_face_with_colour(1.0, 1.0, 1.0)
    elif type == DObjTypes.D_PLANE.value:
        dobj = make_plane(False, None)
    elif type == DObjTypes.D_MATERIAL.value:
        dobj = make_material(0, None, 0)
    elif type == DObjTypes.D_SHAPE.value:
        dobj = make_shape(0, print_int_dynid(id))
    elif type == DObjTypes.D_GADGET.value:
        dobj = make_gadget(0, 0)
    elif type == DObjTypes.D_LABEL.value:
        #! @bug When making a `D_LABEL`, the call to `make_label()`
        #!      compiles incorrectly due to Goddard only declaring
        #!      the functions, not prototyping the functions
        dobj = make_label(None, None, 8, 0, 0, 0)
    elif type == DObjTypes.D_VIEW.value:
        dobj = make_view(None,
                          (VIEW_2_COL_BUF | VIEW_ALLOC_ZBUF | VIEW_UNK_2000 | VIEW_UNK_4000
                           | VIEW_1_CYCLE | VIEW_MOVEMENT | VIEW_DRAW),
                          2, 0, 0, 0, 0, None)
    elif type == DObjTypes.D_ANIMATOR.value:
        dobj = make_animator()
    elif type == DObjTypes.D_LIGHT.value:
        dobj = make_light(0, None, 0)
#        addto_group(gGdLightGroup, dobj)
    else:
        print("dMakeObj(): Unkown object type")

    add_to_dynobj_list(dobj, id)
    print(sDynListCurObj.__class__)
    return dobj


"""*
 * Attach dynamic object `id` to the current active `ObjJoint` object.
 *
 * @note This function doesn't actually do anything.
 """
def d_attach(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    info = get_dynobj_info(id)
    if info == None:
        print("dAttach(",DynIdAsStr(id),"): Undefined object")

    if sDynListCurObj.type != ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        print(sDynListCurInfo.name,": Object '",sDynListCurObj.type,"'(",sDynListCurObj.type,") does not support this function.", "dAttach()")


def group_contains_obj(group, obj):
    objLink = group.link1C
    
    while objLink != None:
        if objLink.obj.number == obj.number:
            return True

        objLink = objLink.next
    
    return False

"""*
 * Attach the current dynamic `GdObj` into the proper subgroup of `obj` and set
 * the "attach flags" of the current dynamic object to `flag`
 """
def d_attach_to(flag, obj):
    attgrp = None
    dynobjPos = GdVec3f() # transformed into attach offset
    objPos = GdVec3f()

    push_dynobj_stash()

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    # find or generate attachment groups
    if obj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        attrgrp = obj.unk1F8
        if attgrp == None:
            attgrp = obj.unk1F8 = make_group(0)
    elif obj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        attgrp = obj.unk1D4
        if attgrp == None:
            attgrp = obj.unk1D4 = make_group(0)
    elif obj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        attgrp = obj.unkB4
        if attgrp == None:
            attgrp = obj.unkB4 = make_group(0)
    elif obj.type == ObjTypeFlag.OBJ_TYPE_ANIMATORS.value:
        attgrp = obj.unk30
        if attgrp == None:
            attgrp = obj.unk30 = make_group(0)
    else:
        print("dAttachTo(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    if group_contains_obj(attgrp, sDynListCurObj):
        return

    addto_group(attgrp, sDynListCurObj)

    if flag & 9:
        d_get_world_pos(dynobjPos)
        set_cur_dynobj(obj)
        d_get_world_pos(objPos)
        dynobjPos.x -= objPos.x
        dynobjPos.y -= objPos.y
        dynobjPos.z -= objPos.z

    pop_dynobj_stash()
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unk1FC = flag
        sDynListCurObj.unk20C = obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk1E4 = flag
        sDynListCurObj.unk1E8 = obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        sDynListCurObj.unkB8 = flag
        sDynListCurObj.unkBC = obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_ANIMATORS.value:
        sDynListCurObj.unk34 = flag
        sDynListCurObj.unk44 = obj
    else:
        print("dAttachTo(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    if flag & 9:
        d_set_att_offset(dynobjPos)

"""*
 * Attach the current dynamic object to dynamic object `id`. This function
 * is a wrapper around `d_attach_to()`
 """
def d_attachto_dynid(flag, id):
    if id == None:
        return
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dAttachTo(\"",DynIdAsStr(id),"\"): Undefined object")

    d_attach_to(flag, info.obj)

#"""*
# * Helper function to copy bytes. Where's memcpy when you need it?
# """
#def copy_bytes(src, dst, num):
#    if num == 0):
#        return
#
#    while (num--):
#        *dst++ = *src++
#
#

"""*
 * Allocate the animation data for `animator` onto the goddard heap.
 * Animation data of type `::GdAnimations.GD_ANIM_9H.value` is converted to a `AnimMtxVec` class,
 * rather than solely byted copied like the other types.
 """
def alloc_animdata(animator):
    pass
#    # probably should be three GdVec3fs, not triangle...
#    # vec0 = position vec1 = scale? rotation? vec2 = translation
#    class GdTriangleF tri           #+58 temp float for converting half to f32?
#    halfarr = [None] * 9                 #+54 data to convert into a AnimMtxVec
#    animDataArr #+48 start of allocated anim data memory
#    datasize                     #+40 anim data allocation size?
#    dataIdx                      #+3C byte count?
#    i                            #+34
#    allocSpace                 #+30 allocated animdata space
#    allocMtxScale = 0.1         #+2C scale postion/rotation of GdAnimations.GD_ANIM_9H.value data
#    curMtxVec     #+28
#    
##    start_memtracker("animdata")

#    animgrp = animator.animdata
#    if animgrp == None:
#        print("no anim group")

#    curAnimSrc = animgrp.link1C.obj
#    if curAnimSrc == None:
#        print("no animation data")

#    # count number of array-ed animation data classs
#    animDst = curAnimSrc
#    animCnt = 0
#    while (animDst++.count >= 0):
#        animDst += 1
#        animCnt += 1
#

#    animDst = gd_malloc_perm(animCnt * sizeof(class AnimDataInfo)) # gd_alloc_perm
#    if (animDataArr = animDst) == None):
#        print("cant allocate animation data")
#

#    for (i = 0 i < animCnt i++):
#        allocSpace = None
#        if curAnimSrc.type != 0):
#            if curAnimSrc.type):
#                == GdAnimations.GD_ANIM_CAMERA.value:
#                    datasize = sizeof(s16[6])
#                    break
#                == GdAnimations.GD_ANIM_3H_SCALED.value:
#                    datasize = sizeof(s16[3])
#                    break
#                == GdAnimations.GD_ANIM_3H.value:
#                    datasize = sizeof(s16[3])
#                    break
#                == GdAnimations.GD_ANIM_6H_SCALED.value:
#                    datasize = sizeof(s16[6])
#                    break
#                == GdAnimations.GD_ANIM_TRI_F_.value2:
#                    datasize = sizeof(f32[3][3])
#                    break
#                """ This function will convert the s16[9] array into a class AnimMtxVec """
#                == GdAnimations.GD_ANIM_9H.value:
#                    datasize = sizeof(class AnimMtxVec)
#                    break
#                == GdAnimations.GD_ANIM_MATRIX.value:
#                    datasize = sizeof(Mat4f)
#                    break
#                else:
#                    print("unknown anim type for allocation")
#                    break
#            ]

#            allocSpace = gd_malloc_perm(curAnimSrc.count * datasize) # gd_alloc_perm
#            if allocSpace == None):
#                print("cant allocate animation data")
#            ]

#            if curAnimSrc.type == GdAnimations.GD_ANIM_9H.value):
#                for (dataIdx = 0 dataIdx < curAnimSrc.count dataIdx++):
#                    halfarr = &((s16(*)[9]) curAnimSrc.data)[dataIdx]
#                    curMtxVec = &((class AnimMtxVec *) allocSpace)[dataIdx]

#                    tri.p0.x = (f32)(*halfarr)[0] * allocMtxScale
#                    tri.p0.y = (f32)(*halfarr)[1] * allocMtxScale
#                    tri.p0.z = (f32)(*halfarr)[2] * allocMtxScale
#                    tri.p1.x = (f32)(*halfarr)[3] * allocMtxScale
#                    tri.p1.y = (f32)(*halfarr)[4] * allocMtxScale
#                    tri.p1.z = (f32)(*halfarr)[5] * allocMtxScale
#                    tri.p2.x = (f32)(*halfarr)[6]
#                    tri.p2.y = (f32)(*halfarr)[7]
#                    tri.p2.z = (f32)(*halfarr)[8]

#                    gd_set_identity_mat4(&curMtxVec.matrix)
#                    gd_rot_mat_about_vec(&curMtxVec.matrix, &tri.p1)
#                    gd_add_vec3f_to_mat4f_offset(&curMtxVec.matrix, &tri.p2)

#                    ((class AnimMtxVec *) allocSpace)[dataIdx].vec.x = tri.p0.x
#                    ((class AnimMtxVec *) allocSpace)[dataIdx].vec.y = tri.p0.y
#                    ((class AnimMtxVec *) allocSpace)[dataIdx].vec.z = tri.p0.z
#                ]
#                curAnimSrc.type = GdAnimations.GD_ANIM_MTX_VEC.value
#            else:
#                copy_bytes(curAnimSrc.data, allocSpace, curAnimSrc.count * datasize)
#            ]
#        ]

#        animDst[i].type = curAnimSrc.type
#        animDst[i].count = curAnimSrc.count
#        animDst[i].data = allocSpace

#        curAnimSrc++ # next anim data class
#

#    animgrp.link1C.obj = (def *) animDataArr
#    stop_memtracker("animdata")
#

"""*
 * Generate or create the various `ObjVertex`, `ObjFace`, and/or
 * `ObjMaterial` when groups of those classures are attached to
 * `shape`. This function is called when `d_set_nodegroup()`,
 * `d_set_planegroup()`, or `d_set_matgroup()` are called
 * when an `ObjShape` is the active dynamic object.
 *
 * @note Face/vertices need to be set before materials
 """
def chk_shapegen(shape):
    
    def make_face_with_colour(r, g, b):
        add_to_stacktrace("make_face")
        newFace = make_object(ObjTypeFlags.OBJ_TYPE_FACES.value)
        newFace.__class__ = ObjFace
        
        newFace.colour.r = r
        newFace.colour.g = g
        newFace.colour.b = b

        newFace.vtxCount = 0
        newFace.mtlId = -1
        newFace.mtl = None

        return newFace
    
    def gd_make_vertex(x, y, z):
        vtx = make_object(ObjTypeFlags.OBJ_TYPE_VERTICES.value)
        vtx.__class__ = ObjVertex
        vtx.id = 0xD1D4

        vtx.pos.x = x
        vtx.pos.y = y
        vtx.pos.z = z

        vtx.initPos.x = x
        vtx.initPos.y = y
        vtx.initPos.z = z

        vtx.scaleFactor = 1.0
        vtx.gbiVerts = None
        vtx.alpha = 1.0

        vtx.normal.x = 0.0
        vtx.normal.y = 1.0
        vtx.normal.z = 0.0

        return vtx
    
    def map_face_materials(faces, mtls):
        mtl = None
        linkFaces = faces.link1C
        while linkFaces != None:
            temp = linkFaces.obj
            face = temp
            linkMtls = mtls.link1C
            while linkMtls != None:
                mtl = linkMtls.obj
                if mtl.id == face.mtlId:
                    break
                
                linkMtls = linkMtls.next

            if linkMtls != None:
                face.mtl = mtl

            linkFaces = linkFaces.next

#    class ObjFace *face        # sp5C made face
#    class ObjVertex *vtx       # sp58 made gdvtx
#    class ObjVertex **vtxbuf   # sp54 heap storage for made gd vtx
#    class ObjGroup *shapeMtls  # sp50
#    class ObjGroup *shapeFaces # sp4C
#    class ObjGroup *shapeVtx   # sp48
#    UNUSED u32 pad44
#    class ObjGroup *madeFaces  # sp40
#    class ObjGroup *madeVtx    # sp3C
#    u32 i                       # sp38
#    class GdVtxData *vtxdata   # sp34
#    class GdFaceData *facedata # sp30
#    oldObjHead    # sp2C

#    start_memtracker("chk_shapegen")
#    add_to_stacktrace("chk_shapegen")
    shapeMtls = shape.mtlGroup
    shapeFaces = shape.faceGroup
    shapeVtx = shape.vtxGroup

    if shapeVtx != None and shapeFaces != None:
        if shapeVtx.linkType & 1 and shapeFaces.linkType & 1: #? needs the double if
            # These Links point to special, compressed data classures
            vtxdata = shapeVtx.link1C.obj
            facedata = shapeFaces.link1C.obj
            if facedata.type != 1:
                print("unsupported poly type")
            if vtxdata.type != 1:
                print("unsupported vertex type")
            if vtxdata.count >= VTX_BUF_SIZE:
                print("shapegen() too many vertices")

            vtxbuf = [None] * VTX_BUF_SIZE
            oldObjHead = gGdObjectList

            for i in range(vtxdata.count):
                vtx = gd_make_vertex(vtxdata.data[i][0], vtxdata.data[i][1], vtxdata.data[i][2])
                vtx.normal.x = vtx.normal.y = vtx.normal.z = 0.0
                vtxbuf[i] = vtx

            madeVtx = make_group_of_type(ObjTypeFlag.OBJ_TYPE_VERTICES.value, oldObjHead, None)

            oldObjHead = gGdObjectList
            for i in range(facedata.count):
                #! @bug Call to `make_face_with_colour()` compiles incorrectly
                #!      due to Goddard only declaring the functions,
                #!      not prototyping the functions
                face = make_face_with_colour(1.0, 1.0, 1.0)
                face.mtlId = facedata.data[i][0]
                face.vertices[0] = vtxbuf[facedata.data[i][1]]
                face.vertices[1] = vtxbuf[facedata.data[i][2]]
                face.vertices[2] = vtxbuf[facedata.data[i][3]]
                vtxbuf[facedata.data[i][1]].normal.x += face.normal.x
                vtxbuf[facedata.data[i][1]].normal.y += face.normal.y
                vtxbuf[facedata.data[i][1]].normal.z += face.normal.z

                vtxbuf[facedata.data[i][2]].normal.x += face.normal.x
                vtxbuf[facedata.data[i][2]].normal.y += face.normal.y
                vtxbuf[facedata.data[i][2]].normal.z += face.normal.z

                vtxbuf[facedata.data[i][3]].normal.x += face.normal.x
                vtxbuf[facedata.data[i][3]].normal.y += face.normal.y
                vtxbuf[facedata.data[i][3]].normal.z += face.normal.z

            if shape.flag & 0x10:
                for i in range(vtxdata.count):
                    vtxbuf[i].normal.x = vtxbuf[i].pos.x
                    vtxbuf[i].normal.y = vtxbuf[i].pos.y
                    vtxbuf[i].normal.z = vtxbuf[i].pos.z
                    vtxbuf[i].normal.normalize()
            else:
                for i in range(vtxdata.count):
                    vtxbuf[i].normal.normalize()
            
            madeFaces = make_group_of_type(ObjTypeFlag.OBJ_TYPE_FACES.value, oldObjHead, None)
            shape.faceGroup = madeFaces
            shape.vtxGroup = madeVtx
    
    if shapeMtls != None:
        if shape.faceGroup:
            map_face_materials(shape.faceGroup, shapeMtls)
        else:
            print("chk_shapegen() please set face group before mats")


"""*
 * Set the "node group" of the current dynamic object to dynamic object `id`.
 * The node group depends on the type of the current dynamic object:
 * * the vertex group is set for `ObjShape`
 * * the joints/weight group is set for `ObjNet`
 * * data is set for `ObjAnimator`
 * * something is set for `ObjGadget`
 """
def d_set_nodegroup(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dSetNodeGroup(\"",DynIdAsStr(id),"\"): Undefined group")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk1C8 = info.obj
        sDynListCurObj.unk1D0 = info.obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        sDynListCurObj.vtxGroup = info.obj
        chk_shapegen(sDynListCurObj)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        sDynListCurObj.unk54 = info.obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_ANIMATORS.value:
        sDynListCurObj.animdata = info.obj
        alloc_animdata(sDynListCurObj)
    else:
        print("dSetNodeGroup(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the material group of the current dynamic `ObjShape` to `id`.
 """
def d_set_matgroup(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dSetMatGroup(\"",DynIdAsStr(id),"\"): Undefined group")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        sDynListCurObj.mtlGroup = info.obj
        chk_shapegen(sDynListCurObj)
    else:
        print("dSetMatGroup(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

#"""*
# * At one time in the past, this set the s and t value of the current
# * dynamic `ObjVertex`. However, this function does nothing now.
# * See `BetaVtx` for a possible remnant of vertex code that had
# * ST coordinates.
# """
#def d_set_texture_st(UNUSED f32 s, UNUSED f32 t):
#    UNUSED u32 pad[2]

#    if sDynListCurObj == None:
#        print("proc_dynlist(): No current object")
#

#
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
#            break # ifdef-ed out?
#        else:
#            print("", ,": Object '", ,"'(",sDynListCurObj.type,") does not support this function.", "dSetTextureST()",
#                         sDynListCurInfo.name, sDynListCurObj.type)
#
#

"""*
 * Set the texture pointer of the current dynamic `ObjMaterial`.
 """
def d_use_texture(texture):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_MATERIALS.value:
        sDynListCurObj.texture = texture
    else:
        print("dUseTexture(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the current dynamic `ObjNet`'s skin group with the vertex group from
 * the dynamic `ObjShape` with `id`.
 """
def d_set_skinshape(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dSetSkinShape(\"",DynIdAsStr(id),"\"): Undefined object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.skinGrp = info.obj.vtxGroup
    else:
        print("dSetSkinShape(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Map the material ids for the `ObjFace`s in the current dynamic `ObjGroup`
 * to pointer to `ObjMaterial`s in the `ObjGroup` `id`.
 *
 * See `map_face_materials()` for more info.
 """
def d_map_materials(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dMapMaterials(\"",DynIdAsStr(id),"\"): Undefined group")

    map_face_materials(sDynListCurObj, info.obj)

"""*
 * Map the vertex ids for the `ObjFace`s in the current dynamic `ObjGroup`
 * to pointer to `ObjVertex` in the `ObjGroup` `id`.
 *
 * See `map_vertices()` for more info.
 """
def d_map_vertices(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dMapVertices(\"",DynIdAsStr(id),"\"): Undefined group")

    map_vertices(sDynListCurObj, info.obj)

"""*
 * In practice, this is used to set the faces of the current
 * active dynamic `ObjShape` to the dynamic group `id` of `ObjFace`s.
 * It also has interactions with `ObjNet`s, but there are no examples
 * of that usage in existing code.
 """
def d_set_planegroup(id):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    info = get_dynobj_info(id)
    if info == None:
        print("dSetPlaneGroup(\"",DynIdAsStr(id),"\"): Undefined group")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk1CC = info.obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        sDynListCurObj.faceGroup = info.obj
        chk_shapegen(sDynListCurObj)
    else:
        print("dSetPlaneGroup(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the shape pointer of the current active dynamic object to the
 * pointer pointed to by `shpPtrptr`.
 """
def d_set_shapeptrptr(shpPtrptr):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if shpPtrptr == None:
        shpPtrptr = None

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unk20 = shpPtrptr
        sDynListCurObj.unk1C8 = 0
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk1A8 = shpPtrptr
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        sDynListCurObj.unkF0 = shpPtrptr
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        sDynListCurObj.unk50 = shpPtrptr
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        sDynListCurObj.unk1C = shpPtrptr
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        sDynListCurObj.unk9C = shpPtrptr
    else:
        print("dSetShapePtrPtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the shape pointer of the current active dynamic object to dynamic
 * `ObjShape` `id`.
 """
def d_set_shapeptr(id):
    if id == None:
        return

    info = get_dynobj_info(id)
    if info == None:
        print("dSetShapePtr(\"",DynIdAsStr(id),"\"): Undefined object", )

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unk20 = info.obj
        sDynListCurObj.unk1C8 = 0
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk1A8 = info.obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        sDynListCurObj.unkF0 = info.obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        sDynListCurObj.unk50 = info.obj
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        sDynListCurObj.unk1C = info.obj
    else:
        print("dSetShapePtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the current active dynamic object to object `id`.
 """
def d_use_obj(id):
    info = get_dynobj_info(id)
    if info == None:
        print("dUseObj(\"",DynIdAsStr(id),"\"): Undefined object")

    sDynListCurObj = info.obj
    sDynListCurInfo = info

    return info.obj

"""*
 * Set the current active dynamic object to `obj`. This object can
 * any type of `GdObj`, not just an object created through the
 * dynmaic object system.
 """
def set_cur_dynobj(obj):
    sDynListCurObj = obj
    sDynListCurInfo = sNullDynObjInfo

"""*
 * Start a dynamic `ObjGroup` identified with `id`.
 """
def d_start_group(id):
    d_makeobj(DObjTypes.D_GROUP.value, id)

"""*
 * Add all dynamic objects created between the start of dynamic `ObjGroup` `id`
 * and this call.
 """
def d_end_group(id):
    info = get_dynobj_info(id) # sp20
    if info == None:
        print("dEndGroup(\"",DynIdAsStr(id),"\"): Undefined group")

    dynGrp = info.obj
    for i in range(info.num + 1, sLoadedDynObjs):
        if sGdDynObjList[i].obj.type != ObjTypeFlag.OBJ_TYPE_GROUPS.value:
            addto_group(dynGrp, sGdDynObjList[i].obj)

"""*
 * Add the current dynamic object to the dynamic `ObjGroup` `id`.
 """
def d_addto_group(id):
    info = get_dynobj_info(id) # sp20
    if info == None:
        print("dAddToGroup(\"",DynIdAsStr(id),"\"): Undefined group")

    targetGrp = info.obj
    addto_group(targetGrp, sDynListCurObj)

"""*
 * Set if `DynId` should be treated as integer values,
 * or as `char *` string pointers.
 *
 * @param isIntBool `True` to interpret ids as integers
 """
def dynid_is_int(isIntBool):
    sGdDynObjIdIsInt = isIntBool


"""*
 * Set the initial position of the current dynamic object
 * to `(x, y, z)`.
 """
def d_set_init_pos(x, y, z):
    dynobj = sDynListCurObj # sp28
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk14.x = x
        dynobj.unk14.y = y
        dynobj.unk14.z = z

        dynobj.unk3C.x = x
        dynobj.unk3C.y = y
        dynobj.unk3C.z = z

        dynobj.unk54.x = x
        dynobj.unk54.y = y
        dynobj.unk54.z = z
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.unk14.x = x
        dynobj.unk14.y = y
        dynobj.unk14.z = z

        dynobj.unk20.x = x
        dynobj.unk20.y = y
        dynobj.unk20.z = z
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dynobj.unk20.x = x
        dynobj.unk20.y = y
        dynobj.unk20.z = z
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dynobj.unk14.x = x
        dynobj.unk14.y = y
        dynobj.unk14.z = z
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        d_set_rel_pos(x, y, z)

        dynobj.initPos.x = x
        dynobj.initPos.y = y
        dynobj.initPos.z = z
    else:
        print("dSetInitPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the velocity of the current active dynamic object. The
 * values of the input `GdVec3f` are copied into the object.
 """
def d_set_velocity(vel):
    dynobj = sDynListCurObj

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk78.x = vel.x
        dynobj.unk78.y = vel.y
        dynobj.unk78.z = vel.z
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.unk50.x = vel.x
        dynobj.unk50.y = vel.y
        dynobj.unk50.z = vel.z
    else:
        print("dSetVelocity(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Read the velocity value of the current dynamic object into `dst`
 *
 * @param[out] dst values are copied to this `GdVec3f`
 """
def d_get_velocity(dst):
    dynobj = sDynListCurObj

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst.x =  dynobj.unk78.x
        dst.y =  dynobj.unk78.y
        dst.z =  dynobj.unk78.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dst.x =  dynobj.unk50.x
        dst.y =  dynobj.unk50.y
        dst.z =  dynobj.unk50.z
    else:
        dst.x = dst.y = dst.z = 0.0

#"""*
# * Set the torque vectore for the current dynamic object.
# * Values from input `GdVec3f` are copied into the object.
# *
# * @note Not called
# """
#def d_set_torque(const class GdVec3f *src):
#    dynobj = sDynListCurObj

#    if sDynListCurObj == None:
#        print("proc_dynlist(): No current object")
#

#
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
#            dynobj.unkA4.x = src.x
#            dynobj.unkA4.y = src.y
#            dynobj.unkA4.z = src.z
#            break
#        else:
#            print("", ,": Object '", ,"'(",sDynListCurObj.type,") does not support this function.", "dSetTorque()",
#                         sDynListCurInfo.name, sDynListCurObj.type)
#
#

"""*
 * Get the initial position of the current dynamic object and
 * store in `dst`.
 """
def d_get_init_pos(dst):
    dynobj = sDynListCurObj

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst.x = dynobj.unk54.x
        dst.y = dynobj.unk54.y
        dst.z = dynobj.unk54.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dst.x = dynobj.unk20.x
        dst.y = dynobj.unk20.y
        dst.z = dynobj.unk20.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        dst.x = dynobj.initPos.x
        dst.y = dynobj.initPos.y
        dst.z = dynobj.initPos.z
    else:
        print("dGetInitPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Get the initial rotation of the current dynamic object and
 * store in `dst`.
 """
def d_get_init_rot(dst):
    dynobj = sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst.x = dynobj.unk6C.x
        dst.y = dynobj.unk6C.y
        dst.z = dynobj.unk6C.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dst.x = dynobj.unk68.x
        dst.y = dynobj.unk68.y
        dst.z = dynobj.unk68.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        dst.x = dst.y = dst.z = 0.0
    else:
        print("dGetInitRot(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Set the position of the current dynamic object.
 *
 * @note This function automatically adjusts the three zoom levels
 *       for an `ObjCamera`.
 """
def d_set_rel_pos(x, y, z):
    dynobj = sDynListCurObj # sp34
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk3C.x = x
        dynobj.unk3C.y = y
        dynobj.unk3C.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dynobj.unk40.x = x
        dynobj.unk40.y = y
        dynobj.unk40.z = z

        dynobj.positions[0].x = x
        dynobj.positions[0].y = y
        dynobj.positions[0].z = z

        dynobj.positions[1].x = x * 1.5 #? 1.5f
        dynobj.positions[1].y = y * 1.5 #? 1.5f
        dynobj.positions[1].z = z * 1.5 #? 1.5f

        dynobj.positions[2].x = x * 2.0
        dynobj.positions[2].y = y * 2.0
        dynobj.positions[2].z = z * 2.0

        dynobj.zoomLevels = 2
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        dynobj.pos.x = x
        dynobj.pos.y = y
        dynobj.pos.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LABELS.value:
        dynobj.vec14.x = x
        dynobj.vec14.y = y
        dynobj.vec14.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dynobj.unk20.x = x
        dynobj.unk20.y = y
        dynobj.unk20.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        pass
    else:
        print("dSetRelPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Offset the current position of the current dynamic object.
 """
def d_addto_rel_pos(src):
    dynobj = sDynListCurObj # sp24

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        dynobj.pos.x += src.x
        dynobj.pos.y += src.y
        dynobj.pos.z += src.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk3C.x += src.x
        dynobj.unk3C.y += src.y
        dynobj.unk3C.z += src.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dynobj.unk20.x += src.x
        dynobj.unk20.y += src.y
        dynobj.unk20.z += src.z
    else:
        print("dAddToRelPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

"""*
 * Store the current dynamic object's position into `dst`.
 """
def d_get_rel_pos(dst):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        dst.x = sDynListCurObj.pos.x
        dst.y = sDynListCurObj.pos.y
        dst.z = sDynListCurObj.pos.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst.x = sDynListCurObj.unk3C.x
        dst.y = sDynListCurObj.unk3C.y
        dst.z = sDynListCurObj.unk3C.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dst.x = sDynListCurObj.unk40.x
        dst.y = sDynListCurObj.unk40.y
        dst.z = sDynListCurObj.unk40.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dst.x = sDynListCurObj.unk20.x
        dst.y = sDynListCurObj.unk20.y
        dst.z = sDynListCurObj.unk20.z
    else:
        print("dGetRelPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Return a pointer to the attached object group of the current
 * dynamic object.
 """
def d_get_att_objgroup():
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")


    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        return  sDynListCurObj.unk1F8
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        return  sDynListCurObj.unk1D4
    else:
        print("dGetAttObjGroup(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    return None
    # No null return due to `print()` being a non-returning function?

"""*
 * Return a pointer to the attached object of the current dynamic object.
 """
def d_get_att_to_obj():
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        return sDynListCurObj.unk20C
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        return sDynListCurObj.unk1E8
    else:
        print("dGetAttToObj(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")
 
    # No null return due to `print()` being a non-returning function?


"""*
 * Store the current dynamic object's scale into `dst`.
 """
def d_get_scale(dst):
    dynobj # sp24

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst.x = dynobj.unk9C.x
        dst.y = dynobj.unk9C.y
        dst.z = dynobj.unk9C.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dst.x = dynobj.unk1AC.x
        dst.y = dynobj.unk1AC.y
        dst.z = dynobj.unk1AC.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        dst.x = 1.0
        dst.y = 1.0
        dst.z = 1.0
    else:
        print("dGetScale(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")



"""*
 * Set the offset of the attached object on the current dynamic object.
 """
def d_set_att_offset(off_x, off_y, off_z):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk200.x = off_x
        dynobj.unk200.y = off_y
        dynobj.unk200.z = off_z

        dynobj.unk54.x = off_x
        dynobj.unk54.y = off_y
        dynobj.unk54.z = off_z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.unk1D8.x = off_x
        dynobj.unk1D8.y = off_y
        dynobj.unk1D8.z = off_z

        dynobj.unk20.x = off_x
        dynobj.unk20.y = off_y
        dynobj.unk20.z = off_z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        pass
    else:
        print("dSetAttOffset(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")



#"""*
# * An incorrectly-coded recursive function that was presumably supposed to
# * set the offset of an attached object. Now, it will only call itself
# * until it encounters a None pointer, which will trigger a `print()`
# * call.
# *
# * @note Not called
# """
#def d_set_att_to_offset(UNUSED u32 a):
#    dynobj # sp3c
#    UNUSED u8 pad[24]

#    if sDynListCurObj == None:
#        print("proc_dynlist(): No current object")
#

#    dynobj = sDynListCurObj
#    push_dynobj_stash()
#
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
#            set_cur_dynobj(dynobj.unk20C)
#            break
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
#            set_cur_dynobj(dynobj.unk1E8)
#            break
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
#            set_cur_dynobj(dynobj.unkBC)
#            break
#        else:
#            print("", ,": Object '", ,"'(",sDynListCurObj.type,") does not support this function.", "dSetAttToOffset()",
#                         sDynListCurInfo.name, sDynListCurObj.type)
#

#    if sDynListCurObj == None:
#        print("dSetAttOffset(): Object '", ,"' isnt attached to anything",
#                     sStashedDynObjInfo.name)
#
#    d_set_att_to_offset(a)
#    pop_dynobj_stash()
#

#"""*
# * Store the offset of the attached object into `dst`.
# *
# * @note Not called
# """
#def d_get_att_offset(class GdVec3f *dst):
#    if sDynListCurObj == None:
#        print("proc_dynlist(): No current object")
#

#
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
#            dst.x =  sDynListCurObj).unk200.x
#            dst.y =  sDynListCurObj).unk200.y
#            dst.z =  sDynListCurObj).unk200.z
#            break
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
#            dst.x =  sDynListCurObj).unk1D8.x
#            dst.y =  sDynListCurObj).unk1D8.y
#            dst.z =  sDynListCurObj).unk1D8.z
#            break
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
#            break
#        else:
#            print("", ,": Object '", ,"'(",sDynListCurObj.type,") does not support this function.", "dGetAttOffset()",
#                         sDynListCurInfo.name, sDynListCurObj.type)
#
#

"""*
 * Get the attached object flags for the current dynamic object.
 """
def d_get_att_flags():
    attflag = None

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        attflag =  sDynListCurObj.unk1FC
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        attflag =  sDynListCurObj.unk1E4
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        attflag =  sDynListCurObj.unkB8
    else:
        print("dGetAttFlags(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    return attflag


"""*
 * Set the world position of the current dynamic object.
 *
 * @note Sets the upper left coordinates of an `ObjView`
 """
def d_set_world_pos(x, y, z):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        sDynListCurObj.unk14.x = x
        sDynListCurObj.unk14.y = y
        sDynListCurObj.unk14.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unk14.x = x
        sDynListCurObj.unk14.y = y
        sDynListCurObj.unk14.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk14.x = x
        sDynListCurObj.unk14.y = y
        sDynListCurObj.unk14.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        sDynListCurObj.unk14.x = x
        sDynListCurObj.unk14.y = y
        sDynListCurObj.unk14.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VIEWS.value:
        sDynListCurObj.upperLeft.x = x
        sDynListCurObj.upperLeft.y = y
        sDynListCurObj.upperLeft.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        sDynListCurObj.pos.x = x
        sDynListCurObj.pos.y = y
        sDynListCurObj.pos.z = z
    else:
        print("dSetWorldPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")



"""*
 * Set the normal of the current dynamic `ObjVertex`. The input `x, y, z` values
 * are normalized into a unit vector before setting the vertex normal.
 """
def d_set_normal(x, y, z):

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    normal = GdVec3f(x, y, z)
    normal.normalize()

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        sDynListCurObj.normal.x = normal.x
        sDynListCurObj.normal.y = normal.y
        sDynListCurObj.normal.z = normal.z
    else:
        print("dSetNormal(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


#"""*
# * Get a pointer to the world position vector of the active
# * dynamic object. This is a pointer inside the actual object.
# *
# * @note Not called.
# """
#class GdVec3f *d_get_world_pos_ptr(def):
#    if sDynListCurObj == None:
#        print("proc_dynlist(): No current object")
#

#
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
#            return & sDynListCurObj).pos
#            break
#        elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
#            return & sDynListCurObj).unk20
#            break
#        else:
#            print("", ,": Object '", ,"'(",sDynListCurObj.type,") does not support this function.", "dGetWorldPosPtr()",
#                         sDynListCurInfo.name, sDynListCurObj.type)
#
#    # No null return due to `print()` being a non-returning function?
#

"""*
 * Copy the world position of the current dynamic object into `dst`.
 """
def d_get_world_pos(dst):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")
    
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        dst.x = sDynListCurObj.pos.x
        dst.y = sDynListCurObj.pos.y
        dst.z = sDynListCurObj.pos.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst.x = sDynListCurObj.unk14.x
        dst.y = sDynListCurObj.unk14.y
        dst.z = sDynListCurObj.unk14.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dst.x = sDynListCurObj.unk14.x
        dst.y = sDynListCurObj.unk14.y
        dst.z = sDynListCurObj.unk14.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dst.x = sDynListCurObj.unk20.x
        dst.y = sDynListCurObj.unk20.y
        dst.z = sDynListCurObj.unk20.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dst.x = sDynListCurObj.unk14.x
        dst.y = sDynListCurObj.unk14.y
        dst.z = sDynListCurObj.unk14.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        dst.x = sDynListCurObj.unk14.x
        dst.y = sDynListCurObj.unk14.y
        dst.z = sDynListCurObj.unk14.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        dst.x = dst.y = dst.z = 0.0
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LABELS.value:
        dst.x = dst.y = dst.z = 0.0
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        dst.x = sDynListCurObj.unk14.x
        dst.y = sDynListCurObj.unk14.y
        dst.z = sDynListCurObj.unk14.z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PLANES.value:
        dst.x = sDynListCurObj.plane28.p0.x
        dst.y = sDynListCurObj.plane28.p0.y
        dst.z = sDynListCurObj.plane28.p0.z

        dst.x += sDynListCurObj.plane28.p1.x
        dst.y += sDynListCurObj.plane28.p1.y
        dst.z += sDynListCurObj.plane28.p1.z

        dst.x *= 0.5 #? 0.5f
        dst.y *= 0.5 #? 0.5f
        dst.z *= 0.5 #? 0.5f
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_ZONES.value:
        dst.x = sDynListCurObj.unk14.p0.x
        dst.y = sDynListCurObj.unk14.p0.y
        dst.z = sDynListCurObj.unk14.p0.z

        dst.x += sDynListCurObj.unk14.p1.x
        dst.y += sDynListCurObj.unk14.p1.y
        dst.z += sDynListCurObj.unk14.p1.z

        dst.x *= 0.5 #? 0.5f
        dst.y *= 0.5 #? 0.5f
        dst.z *= 0.5 #? 0.5f
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        dst.x = sDynListCurObj.position.x
        dst.y = sDynListCurObj.position.y
        dst.z = sDynListCurObj.position.z
    else:
        print("dGetWorldPos(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Create a new dynamic `ObjVertex` at point `pos`.
 *
 * @param[in] pos values are copied to set vertex position
 """
def d_make_vertex(pos):
    d_makeobj(DObjTypes.D_VERTEX.value, AsDynId(None))
    d_set_init_pos(pos.x, pos.y, pos.z)


"""*
 * Scale the current dynamic object by factor `(x, y, z)`.
 *
 * @note Sets the lower right coordinates of an `ObjView`
 """
def d_set_scale(x, y, z):
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    initDynobj = sDynListCurObj
    push_dynobj_stash()

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        initDynobj.unk9C.x = x
        initDynobj.unk9C.y = y
        initDynobj.unk9C.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        initDynobj.unk1AC.x = x
        initDynobj.unk1AC.y = y
        initDynobj.unk1AC.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VIEWS.value:
        initDynobj.lowerRight.x = x
        initDynobj.lowerRight.y = y
        initDynobj.lowerRight.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        pass
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        if initDynobj.unk50 != None:
            scale_verts_in_shape(initDynobj.unk50, x, y, z)
        initDynobj.unk40.x = x
        initDynobj.unk40.y = y
        initDynobj.unk40.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        pass
    else:
        print("dSetScale(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    pop_dynobj_stash()


"""*
 * Set the rotation value of the current active dynamic object.
 """
def d_set_rotation(x, y, z):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk6C.x = x
        dynobj.unk6C.y = y
        dynobj.unk6C.z = z
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.unk68.x = x
        dynobj.unk68.y = y
        dynobj.unk68.z = z
    else:
        print("dSetRotation(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the center of gravity of the current dynamic `ObjNet`.
 """
def d_center_of_gravity(x, y, z):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unkB0.x = x
        sDynListCurObj.unkB0.y = y
        sDynListCurObj.unkB0.z = z
    else:
        print("dCofG(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the shape offset of the current dynamic `ObjJoint`.
 """
def d_set_shape_offset(x, y, z):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unkC0.x = x
        sDynListCurObj.unkC0.y = y
        sDynListCurObj.unkC0.z = z
    else:
        print("dShapeOffset(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Create a new `ObjValPtr` to dynamic object `objId` and attach
 * that valptr to the current dynamic object.
 *
 * @param type `::ValPtrType`
 """
def d_add_valptr(objId, vflags, type, offset):
    valptr # sp28
    info   # sp24

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj

    if vflags == 0x40000:
        info = get_dynobj_info(objId)
        if info == None:
            print("dAddValPtr(\"",DynIdAsStr(objId),"\"): Undefined object")
        
        valptr = make_valptrs(info.obj, vflags, type, offset)
    else:
        valptr = make_valptrs(objId, vflags, type, offset)

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        if dynobj.unk4C == None:
            dynobj.unk4C = make_group(0)
        addto_group(dynobj.unk4C, valptr
        )
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LABELS.value:
        dynobj.valptr = valptr
    else:
        print("dAddValPtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Add a value processing function (`valptrproc_t`) to the current
 * dynamic `ObjLabel`.
 """
def d_add_valproc(proc):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LABELS.value:
        dynobj.valfn = proc
    else:
        print("dAddValProc(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Link a variable pointer to the current active dynamic object.
 * In the final game, this is used to link arrays of raw vertex, face,
 * or animation data to `ObjGroup`s, or to link joints to `ObjAnimator`s.
 """
def d_link_with_ptr(ptr):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj
    
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dynobj.unk30 = ptr
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GROUPS.value:
        link = make_link_to_obj(None, ptr)
        dynobj.link1C = link
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        add_joint2bone(dynobj, ptr)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VIEWS.value:
        dynobj.components = ptr
        dynobj.unk1C = \
        setup_view_buffers(dynobj.namePtr, dynobj,
                   dynobj.upperLeft.x,
                   dynobj.upperLeft.y,
                   dynobj.lowerRight.x,
                   dynobj.lowerRight.y)
        reset_nets_and_gadgets(dynobj.components)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_FACES.value:
        if dynobj.vtxCount >= 4:
            print("too many points")
        
        dynobj.vertices[dynobj.vtxCount] = ptr
        dynobj.vtxCount += 1

        if dynobj.vtxCount >= 3:
            calc_face_normal(dynobj)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_ANIMATORS.value:
        if dynobj.unk14 == None:
            dynobj.unk14 = make_group(0)

        addto_group(dynobj.unk14, ptr)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LABELS.value:
        valptr = make_valptrs(ptr, ObjTypeFlag.OBJ_TYPE_ALL.value, 0, 0)
        dynobj.valptr = valptr
    else:
        print("dLinkWithPtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Link the dynamic object `id` to the current dynamic object by wrapping
 * `d_link_with_ptr()`.
 """
def d_link_with(id):
    origInfo = sDynListCurInfo # sp18

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if id == None:
        return


    info = get_dynobj_info(id)
    if info == None:
        print("dLinkWith(\"",DynIdAsStr(id),"\"): Undefined object")

    d_link_with_ptr(info.obj)
    set_cur_dynobj(origInfo.obj)
    sDynListCurInfo = origInfo


"""*
 * Set the object specific flags of the current dynamic object.
 """
def d_set_flags(flags):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk1BC |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        dynobj.unk104 |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.unk34 |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dynobj.unk2C |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VIEWS.value:
        dynobj.flags |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        dynobj.flag |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dynobj.unk54 |= flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        dynobj.flags |= flags
    else:
        print("dSetFlags(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Clear object specific flags from the current dynamic object.
 """
def d_clear_flags(flags):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unk1BC &= ~flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        sDynListCurObj.unk104 &= ~flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk34 &= ~flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        sDynListCurObj.unk2C &= ~flags
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        sDynListCurObj.unk54 &= ~flags
    else:
        print("dClrFlags(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set variable float parameters on the current dynamic object.
 * These are mainly used for `ObjGadget`s to set the drawing size
 * range.
 """
def d_set_parm_f(param, val):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        if param == PARM_F_ALPHA:
            sDynListCurObj.unk58 = val
        else:
            print("dSetParmf() - unsupported parm.: Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        if param == PARM_F_RANGE_LEFT:
            sDynListCurObj.unk38 = val
        elif param == PARM_F_RANGE_RIGHT:
            sDynListCurObj.unk3C = val
        elif param == PARM_F_VARVAL:
            sDynListCurObj.varval.f = val
        else:
            print("dSetParmf() - unsupported parm.: Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        if param == PARM_F_ALPHA:
            sDynListCurObj.alpha = val
        else:
            print("dSetParmf() - unsupported parm: Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")
    else:
        print("dSetParmf(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")



"""*
 * Set various pointer parameters for the current dynamic object.
 * Normally, this is used to set `char *` pointer for various objects,
 * but it can also set the vertices for an `ObjFace`.
 """
def d_set_parm_ptr(param, ptr):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LABELS.value:
        if param == PARM_PTR_CHAR:
            sDynListCurObj.fmtstr = ptr
        else:
            print("Bad parm")
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VIEWS.value:
        if param == PARM_PTR_CHAR:
            sDynListCurObj.namePtr = ptr
        else:
            print("Bad parm")
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_FACES.value:
        if param == PARM_PTR_OBJ_VTX:
            if sDynListCurObj.vtxCount > 3:
                print("dsetparmp() too many points")
            sDynListCurObj.vertices[sDynListCurObj.vtxCount] = ptr
            sDynListCurObj.vtxCount += 1
        else:
            print("Bad parm")
    else:
        print("dSetParmp(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the generic drawing flags for the current dynamic object.
 """
def d_set_obj_draw_flag(flag):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    sDynListCurObj.drawFlags |= flag


"""*
 * Set an object specific type field for the current dynamic object.
 """
def d_set_type(type):
    dynobj = sDynListCurObj # sp24

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.netType = type
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        dynobj.unk24 = type
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GROUPS.value:
        dynobj.debugPrint = type
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.unk1CC = type
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dynobj.unk60 = type
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_MATERIALS.value:
        dynobj.type = type
    else:
        print("dSetType(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the specific object ID field for the current dynamic object.
 """
def d_set_id(id):
    dynobj = sDynListCurObj # sp24

    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_MATERIALS.value:
        dynobj.id = id
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.id = id
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_VERTICES.value:
        dynobj.id = id
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        dynobj.id = id
    else:
        print("dSetID(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


# TODO: enumerate colors?
"""*
 * Set the colour of the current dynamic object. The input color is an index
 * for `gd_get_colour()`
 """
def d_set_colour_num(colornum):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unk1C8 = colornum
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        sDynListCurObj.unk58 = colornum
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk40 = colornum
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_GADGETS.value:
        sDynListCurObj.unk5C = colornum
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_FACES.value:
        rgbcolor = gd_get_colour(colornum)
        if rgbcolor != None:
            sDynListCurObj.colour.r = rgbcolor.r
            sDynListCurObj.colour.g = rgbcolor.g
            sDynListCurObj.colour.b = rgbcolor.b
            sDynListCurObj.colNum = colornum
        else:
            print("dSetColNum: Unkown colour number")
    else:
        print("dColourNum(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the material ID of the current dynamic `ObjFace`.
 """
def d_set_material(a0, mtlId):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_FACES.value:
        sDynListCurObj.mtlId = mtlId
    else:
        print("dSetMaterial(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the friction vec of the current dynamic `ObjJoint`.
 """
def d_friction(x, y, z):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.unkDC.x = x
        sDynListCurObj.unkDC.y = y
        sDynListCurObj.unkDC.z = z
    else:
        print("dFriction(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")



"""*
 * Set the spring constant of the current dynamic `ObjBone`.
 """
def d_set_spring(spring):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        sDynListCurObj.unk110 = spring
    else:
        print("dSetSpring(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the ambient color of the current dynamic `ObjMaterial`.
 """
def d_set_ambient(r, g, b):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_MATERIALS.value:
        sDynListCurObj.Ka.r = r
        sDynListCurObj.Ka.g = g
        sDynListCurObj.Ka.b = b
    else:
        print("dSetAmbient(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the diffuse color of the current dynamic `ObjMaterial` or `ObjLight`.
 """
def d_set_diffuse(r, g, b):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_MATERIALS.value:
        sDynListCurObj.Kd.r = r
        sDynListCurObj.Kd.g = g
        sDynListCurObj.Kd.b = b
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        sDynListCurObj.diffuse.r = r
        sDynListCurObj.diffuse.g = g
        sDynListCurObj.diffuse.b = b
    else:
        print("dSetDiffuse(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the control type of the current dynamic `ObjNet`.
 """
def d_set_control_type(ctrltype):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.unk210 = ctrltype
    else:
        print("dControlType(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Get a pointer to a `GdPlaneF` in the current dynamic object.
 * If the current object does not have a plane, a pointer to
 * a global plane at (0,0) is returned.
 """
def d_get_plane():
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        return sDynListCurObj.unkBC
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PLANES.value:
        return sDynListCurObj.plane28
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_ZONES.value:
        return sDynListCurObj.unk14
    else:
        return sGdNullPlaneF



"""*
 * Copy the matrix from the current dynamic object into `dst`.
 """
def d_get_matrix(dst):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")


    dynobj = sDynListCurObj

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dst = dynobj.mat128
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dst = dynobj.matE8 
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        dst = dynobj.unkE8
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_PARTICLES.value:
        dst = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_SHAPES.value:
        dst = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    else:
        print("dGetMatrix(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")
    dst = copy.deepcopy(dst)


"""*
 * Set the matrix of the current dynamic object by copying `src` into the object.
 """
def d_set_matrix(src):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.mat128 = copy.deepcopy(src)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.matE8 = copy.deepcopy(src)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        sDynListCurObj.unk64 = copy.deepcopy(src)
    else:
        print("dSetMatrix(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Set the rotation matrix of the current dynamic object by copying
 * the input matrix `src`.
 """
def d_set_rot_mtx(src):
    global sDynListCurObj
    
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        sDynListCurObj.mat128 = copy.deepcopy(src)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        sDynListCurObj.mat168 = copy.deepcopy(src)
    else:
        print("dSetRMatrix(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Get a pointer to the current dynamic object's rotation matrix.
 """
def d_get_rot_mtx_ptr():
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        return sDynListCurObj.mat128
    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        return sDynListCurObj.mat168
    else:
        print("dGetRMatrixPtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    # No null return due to `print()` being a non-returning function?


"""*
 * Copy `src` into the identity matrix of the current dynamic object.
 """
def d_set_idn_mtx(src):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        dynobj.matE8 = copy.deepcopy(src)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        dynobj.mat168 = copy.deepcopy(src)
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_LIGHTS.value:
        dynobj.position.x = src[3][0]
        dynobj.position.y = src[3][1]
        dynobj.position.z = src[3][2]
    else:
        print("dSetIMatrix(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


"""*
 * Get a pointer to the current dynamic object's matrix.
 """
def d_get_matrix_ptr():
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        return sDynListCurObj.mat128
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_CAMERAS.value:
        return sDynListCurObj.unk64
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_BONES.value:
        return sDynListCurObj.mat70
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        return sDynListCurObj.matE8
    else:
        print("dGetMatrixPtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    # No null return due to `print()` being a non-returning function?


"""*
 * Get a pointer to the current dynamic object's identity matrix.
 """
def d_get_idn_mtx_ptr():
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    dynobj = sDynListCurObj

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_NETS.value:
        return dynobj.matE8
    elif sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        return dynobj.mat168
    else:
        print("dGetIMatrixPtr(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")

    # No null return due to `print()` being a non-returning function?


"""*
 * Use the dynamic object system to calculate the distance between
 * two `GdObj`s. The objects don't have to be dynamic objects.
 """
def d_calc_world_dist_btwn(obj1, obj2):
    obj1pos = GdVec3f() # sp34
    obj2pos = GdVec3f() # sp28
    posdiff = GdVec3f() # sp1C

    set_cur_dynobj(obj1)
    d_get_world_pos(obj1pos)
    set_cur_dynobj(obj2)
    d_get_world_pos(obj2pos)

    posdiff.x = obj2pos.x - obj1pos.x
    posdiff.y = obj2pos.y - obj1pos.y
    posdiff.z = obj2pos.z - obj1pos.z

    return posdiff.length()


"""*
 * Create a new weight for the current dynamic `ObjJoint`. The input weight value
 * is out of 100.
 """
def d_set_skin_weight(id, percentWeight):
    if sDynListCurObj == None:
        print("proc_dynlist(): No current object")

    if sDynListCurObj.type == ObjTypeFlag.OBJ_TYPE_JOINTS.value:
        set_skin_weight(sDynListCurObj, id, None,
                        percentWeight / 100.0) #? 100.0f
    else:
        print("dSetSkinWeight(): Object '",sDynListCurInfo.name,"'(",sDynListCurObj.type,") does not support this function.")


def d_start_list():
    pass

def d_stop_list():
    pass

def d_run_list(dynlist):
#    print(dynlist)
    exec(dynlist)
    return sDynListCurObj


dynlist_function_map = {
    "StartList": "d_start_list",
    "StopList": "d_stop_list",
    "UseIntId": "dynid_is_int",
    "SetInitialPosition": "d_set_init_pos",
    "SetRelativePosition": "d_set_rel_pos",
    "SetWorldPosition": "d_set_world_pos",
    "SetNormal": "d_set_normal",
    "SetScale": "d_set_scale",
    "SetRotation": "d_set_rotation",
    "SetHeaderFlag": "d_set_obj_draw_flag",
    "SetFlag": "d_set_flags",
    "ClearFlag": "d_clear_flags",
    "SetFriction": "d_friction",
    "SetSpring": "d_set_spring",
    "JumpToList": "d_run_list", # TODO
    "SetColourNum": "d_set_colour_num",
    "MakeDynObj": "d_makeobj",
    "StartGroup": "d_start_group",
    "EndGroup": "d_end_group",
    "AddToGroup": "d_addto_group",
    "SetType": "d_set_type",
    "SetMaterialGroup": "d_set_matgroup",
    "SetNodeGroup": "d_set_nodegroup",
    "SetSkinShape": "d_set_skinshape",
    "SetPlaneGroup": "d_set_planegroup",
    "SetShapePtrPtr": "d_set_shapeptrptr",
    "SetShapePtr": "d_set_shapeptr",
    "SetShapeOffset": "d_set_shape_offset",
    "SetCenterOfGravity": "d_center_of_gravity",
    "LinkWith": "d_link_with",
    "LinkWithPtr": "d_link_with_ptr",
    "UseObj": "d_use_obj",
    "SetControlType": "d_set_control_type",
    "SetSkinWeight": "d_set_skin_weight",
    "SetAmbient": "d_set_ambient",
    "SetDiffuse": "d_set_diffuse",
    "SetId": "d_set_id",
    "SetMaterial": "d_set_material",
    "MapMaterials": "d_map_materials",
    "MapVertices": "d_map_vertices",
    "Attach": "d_attach",
    "AttachTo": "d_attachto_dynid",
    "SetAttachOffset": "d_set_att_offset",
    "CopyStrToIdBuf": "d_copystr_to_idbuf",
    "SetParamF": "d_set_parm_f",
    "SetParamPtr": "d_set_parm_ptr",
    "MakeNetWithSubGroup": "d_add_net_with_subgroup",
    "AttachNetToJoint": "d_attach_joint_to_net",
    "EndNetSubGroup": "d_end_net_subgroup",
    "MakeVertex": "d_make_vertex",
    "MakeValPtr": "d_add_valptr",
    "UseTexture": "d_use_texture",
    "SetTextureST": "d_set_texture_st",
    "MakeNetFromShapeId": "d_make_netfromshapeid",
    "MakeNetFromShapeDblPtr": "d_make_netfromshape_ptrptr"
}

dynlist_enums = enum_map

custom_data = {}

blend2sm64 = 212.77


def RunListFromFile(filepath, list_name):
    dynlist = LoadList(filepath, list_name)
    d_run_list(dynlist)


def LoadList(filepath, list_name):
    dynlist = ""
    
    try:
        file = open(filepath)
        text = file.read()
        
        # Load dynlist.
        arr_start = text.find(list_name)
        if arr_start != -1:
            arr_start = text.find("{", arr_start) + 1
            arr_end = text.find("}", arr_start)
            dynlist = text[arr_start:arr_end]
            
            dynlist = dynlist.replace(" ", "")
            dynlist = dynlist.replace(",\n", "\n")
            dynlist = dynlist.replace(",//", " #")
            dynlist = dynlist.replace("&", "")
            dynlist = dynlist.replace("TRUE", "True")
            dynlist = dynlist.replace("FALSE", "False")
            dynlist = dynlist.replace("NULL", "None")
            
            for map in dynlist_function_map.items():
                dynlist = dynlist.replace(map[0] + "(", map[1] + "(")
            for map in dynlist_enums.items():
                dynlist = dynlist.replace(map[0], map[1]+"."+map[0]+".value")
            
            dynlist = re.sub(r"\(([a-z][a-z|A-Z|0-9|_]+?)\)", "(custom_data['\g<1>'])", dynlist)
            dynlist = re.sub(r"\(([a-z][a-z|A-Z|0-9|_]+?),", "(custom_data['\g<1>'],", dynlist)
            dynlist = re.sub(r",([a-z][a-z|A-Z|0-9|_]+?)\)", ",custom_data['\g<1>'])", dynlist)
            dynlist = re.sub(r",([a-z][a-z|A-Z|0-9|_]+?),", ",custom_data['\g<1>'],", dynlist)
            print("DYNLIST '", list_name, "' LOADED")
        else:
            print("Couldn't find list!")
    except:
        e = sys.exc_info()[0]
        print("Couldn't Load DynList '",list_name,"':", e)
    finally:
        file.close()
    
    return dynlist        
