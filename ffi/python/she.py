import os
import platform
from ctypes import *

BN254 = 0
BLS12_381 = 5
MCLBN_FR_UNIT_SIZE = 4
MCLBN_FP_UNIT_SIZE = 6

FR_SIZE = MCLBN_FR_UNIT_SIZE
G1_SIZE = MCLBN_FP_UNIT_SIZE * 3
G2_SIZE = MCLBN_FP_UNIT_SIZE * 6
GT_SIZE = MCLBN_FP_UNIT_SIZE * 12

SEC_SIZE = FR_SIZE * 2
PUB_SIZE = G1_SIZE + G2_SIZE
G1_CIPHER_SIZE = G1_SIZE * 2
G2_CIPHER_SIZE = G2_SIZE * 2
GT_CIPHER_SIZE = GT_SIZE * 4

MCLBN_COMPILED_TIME_VAR = (MCLBN_FR_UNIT_SIZE * 10) + MCLBN_FP_UNIT_SIZE

Buffer = c_ubyte * 1536
lib = None

def init(curveType=BN254):
	global lib
	name = platform.system()
	if name == 'Linux':
		libName = 'libmclshe384_256.so'
	elif name == 'Darwin':
		libName = 'libmclshe384_256.dylib'
	elif name == 'Windows':
		libName = 'mclshe384_256.dll'
	else:
		raise RuntimeError("not support yet", name)
	lib = cdll.LoadLibrary(libName)
	ret = lib.sheInit(curveType, MCLBN_COMPILED_TIME_VAR)
	if ret != 0:
		raise RuntimeError("sheInit", ret)
	# custom setup for a function which returns pointer
	lib.shePrecomputedPublicKeyCreate.restype = c_void_p

def setRangeForDLP(hashSize):
	ret = lib.sheSetRangeForDLP(hashSize)
	if ret != 0:
		raise RuntimeError("setRangeForDLP", ret)

def setTryNum(tryNum):
	lib.sheSetTryNum(tryNum)

def hexStr(v):
	s = ""
	for x in v:
		s += format(x, '02x')
	return s

class CipherTextG1(Structure):
	_fields_ = [("v", c_ulonglong * G1_CIPHER_SIZE)]
	def serialize(self):
		buf = Buffer()
		ret = lib.sheCipherTextG1Serialize(byref(buf), len(buf), byref(self.v))
		if ret == 0:
			raise RuntimeError("serialize")
		return buf[0:ret]
	def serializeToHexStr(self):
		return hexStr(self.serialize())

class CipherTextG2(Structure):
	_fields_ = [("v", c_ulonglong * G2_CIPHER_SIZE)]
	def serialize(self):
		buf = Buffer()
		ret = lib.sheCipherTextG2Serialize(byref(buf), len(buf), byref(self.v))
		if ret == 0:
			raise RuntimeError("serialize")
		return buf[0:ret]
	def serializeToHexStr(self):
		return hexStr(self.serialize())

class CipherTextGT(Structure):
	_fields_ = [("v", c_ulonglong * GT_CIPHER_SIZE)]
	def serialize(self):
		buf = Buffer()
		ret = lib.sheCipherTextGTSerialize(byref(buf), len(buf), byref(self.v))
		if ret == 0:
			raise RuntimeError("serialize")
		return buf[0:ret]
	def serializeToHexStr(self):
		return hexStr(self.serialize())

def _enc(CT, enc, encIntVec, neg, p, m):
	c = CT()
	if -0x80000000 <= m <= 0x7fffffff:
		ret = enc(byref(c.v), p, m)
		if ret != 0:
			raise RuntimeError("enc", m)
		return c
	if m < 0:
		minus = True
		m = -m
	else:
		minus = False
	if m >= 1 << (MCLBN_FR_UNIT_SIZE * 64):
		raise RuntimeError("enc:too large m", m)
	a = []
	while m > 0:
		a.append(m & 0xffffffff)
		m >>= 32
	ca = (c_uint * len(a))(*a)
	ret = encIntVec(byref(c.v), p, byref(ca), sizeof(ca))
	if ret != 0:
		raise RuntimeError("enc:IntVec", m)
	if minus:
		ret = neg(byref(c.v), byref(c.v))
		if ret != 0:
			raise RuntimeError("enc:neg", m)
	return c

class PrecomputedPublicKey(Structure):
	def __init__(self):
		self.p = 0
	def create(self):
		if not self.p:
			self.p = c_void_p(lib.shePrecomputedPublicKeyCreate())
			if self.p == 0:
				raise RuntimeError("PrecomputedPublicKey::create")
	def destroy(self):
		lib.shePrecomputedPublicKeyDestroy(self.p)
	def encG1(self, m):
		return _enc(CipherTextG1, lib.shePrecomputedPublicKeyEncG1, lib.shePrecomputedPublicKeyEncIntVecG1, lib.sheNegG1, self.p, m)
	def encG2(self, m):
		return _enc(CipherTextG2, lib.shePrecomputedPublicKeyEncG2, lib.shePrecomputedPublicKeyEncIntVecG2, lib.sheNegG2, self.p, m)
	def encGT(self, m):
		return _enc(CipherTextGT, lib.shePrecomputedPublicKeyEncGT, lib.shePrecomputedPublicKeyEncIntVecGT, lib.sheNegGT, self.p, m)

class PublicKey(Structure):
	_fields_ = [("v", c_ulonglong * PUB_SIZE)]
	def serialize(self):
		buf = Buffer()
		ret = lib.shePublicKeySerialize(byref(buf), len(buf), byref(self.v))
		if ret == 0:
			raise RuntimeError("serialize")
		return buf[0:ret]
	def serializeToHexStr(self):
		return hexStr(self.serialize())
	def encG1(self, m):
		return _enc(CipherTextG1, lib.sheEncG1, lib.sheEncIntVecG1, lib.sheNegG1, byref(self.v), m)
	def encG2(self, m):
		return _enc(CipherTextG2, lib.sheEncG2, lib.sheEncIntVecG2, lib.sheNegG2, byref(self.v), m)
	def encGT(self, m):
		return _enc(CipherTextGT, lib.sheEncGT, lib.sheEncIntVecGT, lib.sheNegGT, byref(self.v), m)
	def createPrecomputedPublicKey(self):
		ppub = PrecomputedPublicKey()
		ppub.create()
		ret = lib.shePrecomputedPublicKeyInit(ppub.p, byref(self.v))
		if ret != 0:
			raise RuntimeError("createPrecomputedPublicKey")
		return ppub

class SecretKey(Structure):
	_fields_ = [("v", c_ulonglong * SEC_SIZE)]
	def setByCSPRNG(self):
		ret = lib.sheSecretKeySetByCSPRNG(byref(self.v))
		if ret != 0:
			raise RuntimeError("setByCSPRNG", ret)
	def serialize(self):
		buf = Buffer()
		ret = lib.sheSecretKeySerialize(byref(buf), len(buf), byref(self.v))
		if ret == 0:
			raise RuntimeError("serialize")
		return buf[0:ret]
	def serializeToHexStr(self):
		return hexStr(self.serialize())
	def getPulicKey(self):
		pub = PublicKey()
		lib.sheGetPublicKey(byref(pub.v), byref(self.v))
		return pub
	def dec(self, c):
		m = c_longlong()
		if isinstance(c, CipherTextG1):
			ret = lib.sheDecG1(byref(m), byref(self.v), byref(c.v))
		elif isinstance(c, CipherTextG2):
			ret = lib.sheDecG2(byref(m), byref(self.v), byref(c.v))
		elif isinstance(c, CipherTextGT):
			ret = lib.sheDecGT(byref(m), byref(self.v), byref(c.v))
		if ret != 0:
			raise RuntimeError("dec")
		return m.value

def neg(c):
	ret = -1
	if isinstance(c, CipherTextG1):
		out = CipherTextG1()
		ret = lib.sheNegG1(byref(out.v), byref(c.v))
	elif isinstance(c, CipherTextG2):
		out = CipherTextG2()
		ret = lib.sheNegG2(byref(out.v), byref(c.v))
	elif isinstance(c, CipherTextGT):
		out = CipherTextGT()
		ret = lib.sheNegGT(byref(out.v), byref(c.v))
	if ret != 0:
		raise RuntimeError("neg")
	return out

def add(cx, cy):
	ret = -1
	if isinstance(cx, CipherTextG1) and isinstance(cy, CipherTextG1):
		out = CipherTextG1()
		ret = lib.sheAddG1(byref(out.v), byref(cx.v), byref(cy.v))
	elif isinstance(cx, CipherTextG2) and isinstance(cy, CipherTextG2):
		out = CipherTextG2()
		ret = lib.sheAddG2(byref(out.v), byref(cx.v), byref(cy.v))
	elif isinstance(cx, CipherTextGT) and isinstance(cy, CipherTextGT):
		out = CipherTextGT()
		ret = lib.sheAddGT(byref(out.v), byref(cx.v), byref(cy.v))
	if ret != 0:
		raise RuntimeError("add")
	return out

def sub(cx, cy):
	ret = -1
	if isinstance(cx, CipherTextG1) and isinstance(cy, CipherTextG1):
		out = CipherTextG1()
		ret = lib.sheSubG1(byref(out.v), byref(cx.v), byref(cy.v))
	elif isinstance(cx, CipherTextG2) and isinstance(cy, CipherTextG2):
		out = CipherTextG2()
		ret = lib.sheSubG2(byref(out.v), byref(cx.v), byref(cy.v))
	elif isinstance(cx, CipherTextGT) and isinstance(cy, CipherTextGT):
		out = CipherTextGT()
		ret = lib.sheSubGT(byref(out.v), byref(cx.v), byref(cy.v))
	if ret != 0:
		raise RuntimeError("sub")
	return out

def mul(cx, cy):
	ret = -1
	if isinstance(cx, CipherTextG1) and isinstance(cy, CipherTextG2):
		out = CipherTextGT()
		ret = lib.sheMul(byref(out.v), byref(cx.v), byref(cy.v))
	elif isinstance(cx, CipherTextG1) and (isinstance(cy, int) or isinstance(cy, long)):
		return _enc(CipherTextG1, lib.sheMulG1, lib.sheMulIntVecG1, lib.sheNegG1, byref(cx.v), cy)
	elif isinstance(cx, CipherTextG2) and (isinstance(cy, int) or isinstance(cy, long)):
		return _enc(CipherTextG2, lib.sheMulG2, lib.sheMulIntVecG2, lib.sheNegG2, byref(cx.v), cy)
	elif isinstance(cx, CipherTextGT) and (isinstance(cy, int) or isinstance(cy, long)):
		return _enc(CipherTextGT, lib.sheMulGT, lib.sheMulIntVecGT, lib.sheNegGT, byref(cx.v), cy)
	if ret != 0:
		raise RuntimeError("mul")
	return out

if __name__ == '__main__':
	init(BLS12_381)
	sec = SecretKey()
	sec.setByCSPRNG()
	print("sec=", sec.serializeToHexStr())
	pub = sec.getPulicKey()
	print("pub=", pub.serializeToHexStr())

	m11 = 1
	m12 = 5
	m21 = 3
	m22 = -4
	c11 = pub.encG1(m11)
	c12 = pub.encG1(m12)
	# dec(enc) for G1
	if sec.dec(c11) != m11: print("err1")

	# add/sub for G1
	if sec.dec(add(c11, c12)) != m11 + m12: print("err2")
	if sec.dec(sub(c11, c12)) != m11 - m12: print("err3")

	# add/sub for G2
	c21 = pub.encG2(m21)
	c22 = pub.encG2(m22)
	if sec.dec(c21) != m21: print("err4")
	if sec.dec(add(c21, c22)) != m21 + m22: print("err5")
	if sec.dec(sub(c21, c22)) != m21 - m22: print("err6")

	# mul const for G1/G2
	if sec.dec(mul(c11, 3)) != m11 * 3: print("err_mul1")
	if sec.dec(mul(c21, 7)) != m21 * 7: print("err_mul2")

	# large integer
	m1 = 0x140712384712047127412964192876419276341
	m2 = -m1 + 123
	c1 = pub.encG1(m1)
	c2 = pub.encG1(m2)
	if sec.dec(add(c1, c2)) != 123: print("err-large11")
	c1 = mul(pub.encG1(1), m1)
	if sec.dec(add(c1, c2)) != 123: print("err-large12")

	c1 = pub.encG2(m1)
	c2 = pub.encG2(m2)
	if sec.dec(add(c1, c2)) != 123: print("err-large21")
	c1 = mul(pub.encG2(1), m1)
	if sec.dec(add(c1, c2)) != 123: print("err-large22")

	c1 = pub.encGT(m1)
	c2 = pub.encGT(m2)
	if sec.dec(add(c1, c2)) != 123: print("err-large31")
	c1 = mul(pub.encGT(1), m1)
	if sec.dec(add(c1, c2)) != 123: print("err-large32")

	mt = -56
	ct = pub.encGT(mt)
	if sec.dec(ct) != mt: print("err7")

	# mul G1 and G2
	if sec.dec(mul(c11, c21)) != m11 * m21: print("err8")

	# use precomputedPublicKey for performance
	ppub = pub.createPrecomputedPublicKey()
	c1 = ppub.encG1(m11)
	if sec.dec(c1) != m11: print("err9")

	# large integer for precomputedPublicKey
	m1 = 0x140712384712047127412964192876419276341
	m2 = -m1 + 123
	c1 = ppub.encG1(m1)
	c2 = ppub.encG1(m2)
	if sec.dec(add(c1, c2)) != 123: print("err10")
	c1 = ppub.encG2(m1)
	c2 = ppub.encG2(m2)
	if sec.dec(add(c1, c2)) != 123: print("err11")
	c1 = ppub.encGT(m1)
	c2 = ppub.encGT(m2)
	if sec.dec(add(c1, c2)) != 123: print("err12")

	import sys
	if sys.version_info.major >= 3:
		import timeit
		N = 100000
		print(str(timeit.timeit("pub.encG1(12)", number=N, globals=globals()) / float(N) * 1e3) + "msec")
		print(str(timeit.timeit("ppub.encG1(12)", number=N, globals=globals()) / float(N) * 1e3) + "msec")

	ppub.destroy() # necessary to avoid memory leak

