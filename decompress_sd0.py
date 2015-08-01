import argparse
import os.path
import zlib

def decompress(in_path, out_path):
	with open(in_path, "rb") as in_file:
		data = in_file.read()

	assert data[:5] == b"sd0\x01\xff"
	pos = 5
	with open(out_path, "wb") as out_file:
		while pos < len(data):
			length = int.from_bytes(data[pos:pos+4], "little")
			pos += 4
			out_file.write(zlib.decompress(data[pos:pos+length]))
			pos += length

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("in_path")
	parser.add_argument("--out_path", help="If not provided, output file is in the script directory")
	args = parser.parse_args()
	if args.out_path is None:
		filename, ext = os.path.splitext(os.path.basename(args.in_path))
		args.out_path = filename+"_decompressed"+ext

	decompress(args.in_path, args.out_path)

	print("Decompressed file:", args.out_path)
