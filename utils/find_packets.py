import argparse
import os
import re
import zipfile

def find_packets(capture_dir, pattern):
	zips = [os.path.join(dirpath, f) for dirpath, dirnames, files in os.walk(capture_dir) for f in files if f.endswith('.zip')]
	for zip_path in zips:
		with zipfile.ZipFile(zip_path) as zip:
			filenames = [i for i in zip.namelist() if re.search(re.escape(pattern), i) is not None and "of" not in i]
			for filename in filenames:
				yield os.path.join(zip_path, filename), zip.read(filename)

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("capture_dir")
	parser.add_argument("pattern")
	args = parser.parse_args()
	for filename, data in find_packets(args.capture_dir, args.pattern):
		print(filename)
