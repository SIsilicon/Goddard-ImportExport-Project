import copy
from enum import Enum

import gd_math
from gd_math import *

enum_map = {}
def register_enums(enum_class):
    for val in enum_class:
        enum_map[val.name] = enum_class.__name__

class GdColour:
    r = g = b = 0

""" dynlist entries and types """
class DynUnion:
    def __init__(self):
        self.ptr, self.str, self.word

class DynList:
    def __init__(self):
        self.cmd, self.w1, self.w2, self.vec

""" Goddard Code Object classs """
""" Object Type Flags """
class ObjTypeFlag(Enum):
    OBJ_TYPE_GROUPS    = 0x00000001
    OBJ_TYPE_BONES     = 0x00000002
    OBJ_TYPE_JOINTS    = 0x00000004
    OBJ_TYPE_PARTICLES = 0x00000008
    OBJ_TYPE_SHAPES    = 0x00000010
    OBJ_TYPE_NETS      = 0x00000020
    OBJ_TYPE_PLANES    = 0x00000040
    OBJ_TYPE_FACES     = 0x00000080
    OBJ_TYPE_VERTICES  = 0x00000100
    OBJ_TYPE_CAMERAS   = 0x00000200
    # 0x400 was not used
    OBJ_TYPE_MATERIALS = 0x00000800
    OBJ_TYPE_WEIGHTS   = 0x00001000
    OBJ_TYPE_GADGETS   = 0x00002000
    OBJ_TYPE_VIEWS     = 0x00004000
    OBJ_TYPE_LABELS    = 0x00008000
    OBJ_TYPE_ANIMATORS = 0x00010000
    OBJ_TYPE_VALPTRS   = 0x00020000
    # 0x40000 was not used
    OBJ_TYPE_LIGHTS    = 0x00080000
    OBJ_TYPE_ZONES     = 0x00100000
    OBJ_TYPE_UNK200000 = 0x00200000

    """ This constant seems to be used to indicate the type of any or all objects """
    OBJ_TYPE_ALL = 0x00FFFFFF
register_enums(ObjTypeFlag)


#/ Flags for the drawFlags field of an GdObj
class ObjDrawingFlags(Enum):
    OBJ_DRAW_UNK01     = 0x01
    OBJ_NOT_DRAWABLE   = 0x02 #/< This `GdObj` shouldn't be drawn when updating a scene
    OBJ_PICKED         = 0x04 #/< This `GdObj` is held by the cursor
    OBJ_IS_GRABBALE    = 0x08 #/< This `GdObj` can be grabbed/picked by the cursor
    OBJ_USE_ENV_COLOUR = 0x10
register_enums(ObjDrawingFlags)


"""*
 * The base of classure of all of Goddard's objects. It is present as a "header"
 * at the beginning of all `ObjX` classures, and as such, this type is used
 * when he need to generalize code to take different `ObjX`es.
 * It is also a linked list node classure with `prev` and `next` pointers.
 """
class GdObj:
    prev = next = None
    objDrawFn = type = None
    number = None #/< the index of this `GdObj` in the linked list
    drawFlags = None #/< enumerated in `::ObjDrawingFlags`


""" Used to create a linked list of objects (or data)
** within an ObjGroup """
class Links:
    prev = next = obj = None

""" These are the compressed versions of ObjFace or ObjVertex that are
** pointed to by Links in the faceGroup and vtxGroup, if Group.linkType
** is set to 0x01. See `chk_shapegen` """
class GdFaceData:
    count = type = data = None
    
    def __init__(self, count, type, data):
        self.count = count
        self.type = type
        self.data = data

class GdVtxData:
    count = type = data = None
    
    def __init__(self, count, type, data):
        self.count = count
        self.type = type
        self.data = data

class ObjGroup(GdObj):
    prev = next = None
    link1C = None #/< Head of a linked list for objects contained in this group
    link20 = None # what is this second one used for?
    groupObjTypes = 0 #/< OR'd collection of type flags for all objects in this group
    objCount = 0
    debugPrint = None # might also be a type?
    linkType = 1
    name = 0 #/< possibly, only referenced in old code
    id = 0

""" Known linkTypes
 * 0x00 : Normal (link to GdObj)
 * 0x01 : Compressed (vtx or face data)
 """
class ObjBone(GdObj):
    prev = next = None   # maybe, based on make_bone
    mat70 = None
    matB0 = None
    id = None
""" sizeof = 0x124 """

class ObjJoint(GdObj):
    unk1F8 = None
    prevjoint = None # prev joint? linked joint?
    nextjoint = None
    matE8 = None     #matrix4x4
    mat128 = None    # "rot matrix"
    mat168 = None    # "id matrix"
    id = None
""" sizeof = 0x22C """

""" Particle Types (+60)
   3 = Has groups of other particles in 6C?
"""

class ObjParticle(GdObj):
    id = None


class ObjShape(GdObj):
    prevShape = None
    nextShape = None
    faceGroup = None  #""" face group based on get_3DG1_shape """
    vtxGroup = None  #""" vtx group based on get_3DG1_shape """
    gdDls = [0, 0, 0]
    unk24 = None #""" group for type 2 shapenets only ? """
    mtlGroup = None  #""" what does this group do? materials? """
    faceCount = None   #""" face count? based on get_3DG1_shape """
    vtxCount = None   #""" vtx count? based on get_3DG1_shape """
    id = None
    flag = None # what are the flag values? only from dynlists?
    name = None

""" 0x44 Flag Values
 * 0x01 -
 * 0x10 - Use vtx position as vtx normal? (`chk_shapegen`)
 """

""" netTypes
 * 0 - else?
 * 1 - shape net
 * 2 - something about the shape unk24 group having vertices too?
 * 3 - joints?
 * 4 - dynamic net? bone net?
 * 5 - particle net?
 * 6 - stub
 * 7 -
 """

class ObjNet(GdObj):
    matE8 = GdMat4f()
    mat128 = GdMat4f()
    mat168 = GdMat4f()  # "rotation matrix"
    skinGrp = None   # SkinGroup (from reset_weight) (joints and bones)
    netType = None 

    unk14 = GdVec3f()
    unk50 = GdVec3f()
    unkA4 = GdVec3f()
    unk20 = GdVec3f()
    unk68 = GdVec3f()
    unk1AC = GdVec3f()
    unk1D8 = GdVec3f()
    unk1D4 = None
    unk1A8 = None
    unk1C8 = None
    unk1CC = None
    unk1D0 = None
    netType = 0
    unk210 = 0
    unk21C = None
    unk34 = 0
    unk3C = 1
    unk40 = 0
""" sizeof = 0x220 """

class ObjPlane(GdObj):
    id = None
    plane28 = None #position plane?
""" sizeof = 0x44"""

class ObjVertex(GdObj):
    initPos = None
    pos = None     # rel position? world pos? both are set with the same value..
    normal = None  # normal? also color (like gbi?)
    id = None
    scaleFactor = None
    alpha = None
    gbiVerts = None

class VtxLink:
    prev = None; next = None; data = None

class ObjFace(GdObj):
    colour = None
    colNum = -1   # "colour" index
    normal = GdVec3f()
    vtxCount = 0
    vertices = []   # these can also be s32 indices? which are then replaced by `find_thisface_verts`
    mtlId = -1 # from compressed GdFaceData -1 == coloured face?
    mtl = None # initialize to None set by `map_face_materials` from mtlId
""" sizeof = 0x4C """

class ObjCamera(GdObj):
    prev = None; next = None
    id = None
    positions = None # zoom positions (*1, *1.5, *2, empty fourth)
    zoomLevels = None # max number of zoom positions
    zoom = None # index into position vec array
""" sizeof = 0x190 """

class GdMtlTypes(Enum):
    GD_MTL_STUB_DL = 0x01
    GD_MTL_BREAK = 0x04
    GD_MTL_SHINE_DL = 0x10
    GD_MTL_TEX_OFF = 0x20
    GD_MTL_LIGHTS = 0x40 # uses else ==

class ObjMaterial(GdObj):
    id = None
    name = None
    type = None
    Ka = GdVec3f()  # ambient color
    Kd = GdVec3f()  # diffuse color
    gddlNumber = None
""" sizeof = 0x60 """

class ObjWeight(GdObj):
    id = None   #id
    vec20 = None    #based on func_80181894? maybe a GdPlaneF?
""" sizeof = 0x40 """

""" This union is used in ObjGadget for a variable typed field.
** The type can be found by checking group unk4C """
class ObjVarVal:
    i = None; f = None; l = None


class ObjGadget(GdObj):
    varval = None #retype and rename varval30
""" sizeof = 0x60 """

class GdViewFlags(Enum):
    VIEW_2_COL_BUF      = 0x000008
    VIEW_ALLOC_ZBUF     = 0x000010
    VIEW_SAVE_TO_GLOBAL = 0x000040
    VIEW_DEFAULT_PARENT = 0x000100
    VIEW_BORDERED       = 0x000400
    VIEW_UPDATE         = 0x000800
    VIEW_UNK_1000       = 0x001000 # used in setup_view_buffers
    VIEW_UNK_2000       = 0x002000 # only see together with 0x4000
    VIEW_UNK_4000       = 0x004000
    VIEW_COLOUR_BUF     = 0x008000
    VIEW_Z_BUF          = 0x010000
    VIEW_1_CYCLE        = 0x020000
    VIEW_MOVEMENT       = 0x040000
    VIEW_DRAW           = 0x080000
    VIEW_WAS_UPDATED    = 0x100000
    VIEW_LIGHT          = 0x200000
register_enums(GdViewFlags)


class ObjView(GdObj):
    id = None
    activeCam = None # is this really active?
    components = None # camera + joints + nets, etc..?
    lights = None     # only lights?
    pickedObj = None # selected with cursor (`update_view`)
    flags = None
    upperLeft = None # position vec?
    lowerRight = None
    clipping = None # z-coordinate of (x: near, y: far) clipping plane?
    namePtr = None
    gdDlNum = None   # gd dl number
    colour = None
    parent = None # maybe not a true parent, but link to buffers in parent?
    zbuf = None
    colourBufs = None # frame buffers?
""" sizeof = 0xA0 """


#typedef union ObjVarVal * (*valptrproc_t)(union ObjVarVal *, union ObjVarVal)

class ObjLabel(GdObj):
    vec14 = None
    fmtstr = None
    valptr = None
    valfn = None

""" unk30 types:
 * 3 = f32? f32 pointer?
*"""

class ObjAnimator(GdObj):
    animdata = None  #animation data? a group, but the link points to something weird..

""" Animation Data Types """
class GdAnimations(Enum):
    GD_ANIM_EMPTY     = 0  # Listed types are how the data are arranged in memory maybe not be exact type
    GD_ANIM_MATRIX    = 1  # f32[4][4]
    GD_ANIM_TRI_F_2   = 2  # f32[3][3]
    GD_ANIM_9H        = 3  # s16[9]
    GD_ANIM_TRI_F_4   = 4  # f32[3][3]
    GD_ANIM_STUB      = 5
    GD_ANIM_3H_SCALED = 6  # s16[3]
    GD_ANIM_3H        = 7  # s16[3]
    GD_ANIM_6H_SCALED = 8  # s16[6]
    GD_ANIM_MTX_VEC   = 9  # {f32 mtx[4][4] f32 vec[3]}
    GD_ANIM_CAMERA    = 11  # s16[6]
register_enums(GdAnimations)


""" This class is pointed to by the `obj` field in Links class in the `animdata` ObjGroup """
class AnimDataInfo:
    count = None  # count or -1 for end of array of AnimDataInfo classures
    type = None  # types are used in "move_animator"
    data = None # points to an array of `type` data

""" GD_ANIM_MTX_VEC (9) type """
class AnimMtxVec:
    matrix = None
    vec = None  # seems to be a scale vec

class ValPtrType(Enum):
    OBJ_VALUE_INT   = 1
    OBJ_VALUE_FLOAT = 2

class ObjValPtrs(GdObj):
    obj = None   # maybe just a def *?
    offset = None
    datatype = None
""" sizeof = 0x24 """

class GdLightFlags(Enum):
    LIGHT_UNK02 = 0x02 # old type of light?
    LIGHT_NEW_UNCOUNTED = 0x10
    LIGHT_UNK20 = 0x20 # new, actually used type of light? used for phong shading?

class ObjLight(GdObj):
    id = None
    name = None
    flags = None
    diffuse = GdVec3f()
    colour = GdColour()
    position = GdVec3f()
    unk30 = 1.0
    unk4C = 0
    flags = 0
    unk98 = 0
    unk40 = 0
    unk68 = GdVec3f()
""" sizeof = 0xA0 """

class ObjZone(GdObj):
    pass
""" sizeof = 0x38"""

# parameters types for `d_set_parm_ptr()`
class DParmPtr(Enum):
    PARM_PTR_OBJ_VTX = 1 #< parameter is an `ObjVertex` to add to an `ObjFace`
    PARM_PTR_CHAR    = 5  #< parameter is a `char *`
register_enums(DParmPtr)

# parameters for `d_set_parm_f()`
class DParmF(Enum):
    PARM_F_ALPHA = 1       #< Set the alpha value for an `ObjShape` or `ObjVertex`
    PARM_F_RANGE_LEFT = 2  #< Set the left range for an `ObjGadget`
    PARM_F_RANGE_RIGHT = 3 #< Set the right range for an `ObjGadget`
    PARM_F_VARVAL = 6       #< Set the float variable value union in an `ObjGadget`
register_enums(DParmF)

# `d_makeobj()` object types
class DObjTypes(Enum):
    D_CAR_DYNAMICS  = 0
    D_NET           = 1
    D_JOINT         = 2
    D_ANOTHER_JOINT = 3
    D_CAMERA        = 4
    D_VERTEX        = 5
    D_FACE          = 6
    D_PLANE         = 7
    D_BONE          = 8
    D_MATERIAL      = 9
    D_SHAPE         = 10
    D_GADGET        = 11
    D_LABEL         = 12
    D_VIEW          = 13
    D_ANIMATOR      = 14
    D_DATA_GRP      = 15 #< An `ObjGroup` that links to raw vertex or face data
    D_PARTICLE      = 16
    D_LIGHT         = 17
    D_GROUP         = 18
register_enums(DObjTypes)