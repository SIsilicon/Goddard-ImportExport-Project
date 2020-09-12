import copy
import math

GD_X_AXIS = 0
GD_Y_AXIS = 0
GD_Z_AXIS = 0

DEG_PER_RAD = 57.29577950560105


""" Vector Types """
class GdVec3f:
    x = y = z = 0
    
    def length(self):
        return sqrt(self.x*self.x + self.y*self.y + self.z*self.z)

    def normalize(self):
        length = self.length()
        self.x /= length
        self.y /= length
        self.z /= length

class GdPlaneF:
    p0 = GdVec3f()
    p1 = GdVec3f()

class GdTriangleF:
    p0 = GdVec3f()
    p1 = GdVec3f()
    p2 = GdVec3f()


def GdMat4f():
    return copy.deepcopy([[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])

def get_identity_matrix():
    return copy.deepcopy([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])


"""
 * Creates a rotation matrix to multiply the primary matrix by.
 * s/c are sin(angle)/cos(angle). That angular rotation is about vector
 * 'vec'.
 * 
 * Matrix has form-
 *
 * | (1-c)z^2+c (1-c)zy-sx (1-c)xz-sy 0 | 
 * | (1-c)zy-sx (1-c)y^2+c (1-c)xy-sz 0 |
 * | (1-c)xz-sy (1-c)xy-sz (1-c)x^2+c 0 |
 * |      0          0          0     1 |
"""
def gd_create_rot_matrix(mtx, vec, s, c):
    rev = GdVec3f()
    rev.z = vec.x
    rev.y = vec.y
    rev.x = vec.z

    oneMinusCos = 1.0 - c

    mtx[0][0] = oneMinusCos * rev.z * rev.z + c
    mtx[0][1] = oneMinusCos * rev.z * rev.y + s * rev.x
    mtx[0][2] = oneMinusCos * rev.z * rev.x - s * rev.y
    mtx[0][3] = 0.0

    mtx[1][0] = oneMinusCos * rev.z * rev.y - s * rev.x
    mtx[1][1] = oneMinusCos * rev.y * rev.y + c
    mtx[1][2] = oneMinusCos * rev.y * rev.x + s * rev.z
    mtx[1][3] = 0.0

    mtx[2][0] = oneMinusCos * rev.z * rev.x + s * rev.y
    mtx[2][1] = oneMinusCos * rev.y * rev.x - s * rev.z
    mtx[2][2] = oneMinusCos * rev.x * rev.x + c
    mtx[2][3] = 0.0

    mtx[3][0] = 0.0
    mtx[3][1] = 0.0
    mtx[3][2] = 0.0
    mtx[3][3] = 1.0


"""
 * Creates a rotation matrix about vector 'vec' with ang in degrees.
"""
def gd_create_rot_mat_angular(mtx, vec, ang):
    s = math.sin(ang / (DEG_PER_RAD / 2.0))
    c = math.cos(ang / (DEG_PER_RAD / 2.0))

    gd_create_rot_matrix(mtx, vec, s, c)


"""
 * Multiplies two Mat4f matrices and puts it in dst.
"""
def gd_mult_mat4f(mA, mB, dst):
    def MAT4_DOT_PROD(A, B, R, row, col):
        R[row][col] = A[row][0] * B[0][col]
        R[row][col] += A[row][1] * B[1][col]
        R[row][col] += A[row][2] * B[2][col]
        R[row][col] += A[row][3] * B[3][col]


    def MAT4_MULTIPLY(A, B, R):
        MAT4_DOT_PROD(A, B, R, 0, 0)
        MAT4_DOT_PROD(A, B, R, 0, 1)
        MAT4_DOT_PROD(A, B, R, 0, 2)
        MAT4_DOT_PROD(A, B, R, 0, 3)
        MAT4_DOT_PROD(A, B, R, 1, 0)
        MAT4_DOT_PROD(A, B, R, 1, 1)
        MAT4_DOT_PROD(A, B, R, 1, 2)
        MAT4_DOT_PROD(A, B, R, 1, 3)
        MAT4_DOT_PROD(A, B, R, 2, 0)
        MAT4_DOT_PROD(A, B, R, 2, 1)
        MAT4_DOT_PROD(A, B, R, 2, 2)
        MAT4_DOT_PROD(A, B, R, 2, 3)
        MAT4_DOT_PROD(A, B, R, 3, 0)
        MAT4_DOT_PROD(A, B, R, 3, 1)
        MAT4_DOT_PROD(A, B, R, 3, 2)
        MAT4_DOT_PROD(A, B, R, 3, 3)

    res = GdMat4f()
    
    MAT4_MULTIPLY(mA, mB, res)
    dst = res


"""
 * Rotates a mat4f matrix about a given axis
 * by a set angle in degrees.
"""
def gd_absrot_mat4(mtx, axisnum, ang):
    rMat = GdMat4f()
    rot = GdVec3f()

    if axisnum == GD_X_AXIS:
        rot.x = 1.0
        rot.y = 0.0
        rot.z = 0.0
    elif axisnum == GD_Y_AXIS:
        rot.x = 0.0
        rot.y = 1.0
        rot.z = 0.0
    elif axisnum == GD_Z_AXIS:
        rot.x = 0.0
        rot.y = 0.0
        rot.z = 1.0

    gd_create_rot_mat_angular(rMat, rot, ang / 2.0) #? 2.0f
    gd_mult_mat4f(mtx, rMat, mtx)


"""
 * Rotates the matrix 'mtx' about the vector given.
 """
def gd_rot_mat_about_vec(mtx, vec):
    if vec.x != 0.0:
        gd_absrot_mat4(mtx, GD_X_AXIS, vec.x)
    if vec.y != 0.0:
        gd_absrot_mat4(mtx, GD_Y_AXIS, vec.y)
    if vec.z != 0.0:
        gd_absrot_mat4(mtx, GD_Z_AXIS, vec.z)


"""
 * Adds each component of a vector to the
 * translation column of a mat4f matrix.
 """
def gd_add_vec3f_to_mat4f_offset(mtx, vec):
    mtx[3][0] += vec.x
    mtx[3][1] += vec.y
    mtx[3][2] += vec.z

