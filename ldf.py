from pyraknet.bitstream import BitStream, c_bool, c_float, c_int, c_int64, c_ubyte, c_uint

def from_ldf(ldf):
	ldf_dict = {}
	if isinstance(ldf, BitStream):
		for _ in range(ldf.read(c_uint)):
			encoded_key = ldf.read(bytes, length=ldf.read(c_ubyte))
			key = encoded_key.decode("utf-16-le")
			data_type_id = ldf.read(c_ubyte)
			if data_type_id == 0:
				value = ldf.read(str, length_type=c_uint)
			elif data_type_id == 1:
				value = ldf.read(c_int)
			elif data_type_id == 3:
				value = ldf.read(c_float)
			elif data_type_id == 5:
				value = ldf.read(c_uint)
			elif data_type_id == 7:
				value = ldf.read(c_bool)
			elif data_type_id in (8, 9):
				value = ldf.read(c_int64)
			elif data_type_id == 13:
				value = ldf.read(bytes, length=ldf.read(c_uint))
			else:
				raise NotImplementedError(key, data_type_id)
			ldf_dict[key] = data_type_id, value
	else:
		raise NotImplementedError

	return ldf_dict
