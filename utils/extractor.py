import os
import subprocess
import sys
import tempfile
import tkinter.filedialog as filedialog
from tkinter import END, X
from typing import Set

import viewer

class Extractor(viewer.Viewer):
	def __init__(self):
		super().__init__()
		self.records = {}

	def create_widgets(self) -> None:
		super().create_widgets(create_inspector=False)
		self.menubar.add_command(label="Extract Selected", command=self._extract_selected)

		self.tree.bind("<Double-Button-1>", self._show_selected)
		self.tree.bind("<Return>", self._show_selected)

		self.set_headings("Size (Bytes)", treeheading="Filename", treewidth=1600)

	def tree_insert_path(self, path: str, values=()) -> None:
		dir, filename = os.path.split(path)
		if not self.tree.exists(dir):
			self.tree_insert_path(dir)
		self.tree.insert(dir, END, iid=path, text=filename, values=values)

	def askopener(self):
		raise NotImplementedError

	def load(self, path: str) -> None:
		self.records.clear()

	def extract_data(self, path: str) -> bytes:
		raise NotImplementedError

	def _show_selected(self, _) -> None:
		if len(self.tree.selection()) > 10:
			return
		for path in self.tree.selection():
			if self.tree.get_children(path):
				continue # is directory

			data = self.extract_data(path)
			tempfile_path = os.path.join(tempfile.gettempdir(), os.path.basename(path))
			with open(tempfile_path, "wb") as file:
				file.write(data)

			if sys.platform == "win32":
				os.startfile(tempfile_path)
			else:
				opener = "open" if sys.platform == "darwin" else "xdg-open"
				subprocess.call([opener, tempfile_path])

	def _extract_selected(self) -> None:
		outdir = filedialog.askdirectory(title="Select output directory")
		if not outdir:
			return
		paths = set()
		for path in self.tree.selection():
			paths.update(self._get_leaves(path))

		for path in self.step_superbar(paths, "Extracting files"):
			self._save_path(outdir, path)

	def _save_path(self, outdir: str, path: str) -> None:
		data = self.extract_data(path)
		dir, filename = os.path.split(path)
		out = os.path.join(outdir, dir)
		os.makedirs(out, exist_ok=True)
		with open(os.path.join(out, filename), "wb") as file:
			file.write(data)

	def _get_leaves(self, path: str) -> Set[str]:
		output = set()
		if self.tree.get_children(path):
			for child in self.tree.get_children(path):
				output.update(self._get_leaves(child))
		elif path in self.records:
			output.add(path)
		return output
