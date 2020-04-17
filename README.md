# utils
## Utilities for working with LEGO Universe file formats and network packets.
### Created by lcdr
### Source repository at https://github.com/lcdr/utils/
### License: AGPL v3

### Included utilities:

* captureviewer - Graphical viewer for parsing and displaying LU network captures. Opens .zip files containing .bin packets in our capture naming format.
* luzviewer - Graphical viewer for parsing and displaying LU maps saved as .luz and .lvl files. Can open the .luz files in your LU client.
* pkextractor - Graphical viewer and extractor for parsing .pk files (used by LU to pack assets) and displaying their contents. Can extract single files by double-clicking, and can also extract the entire archive to a specified folder.
* lifextractor - Graphical viewer and extractor for parsing .lif files (used by LDD to pack assets) and displaying their contents. Can extract single files by double-clicking, and can also extract the entire archive to a specified folder.
* fdb_to_sqlite - Command line script to convert the information from the FDB database format used by LU to SQLite.
* decompress_sd0 - Command line script to decompress LU's sd0 file format / compression scheme.

### Requirements:
* Python 3.6
* https://github.com/lcdr/bitstream for some scripts

### Installation

`pip install hg+https://github.com/lcdr/utils` should handle the installation automatically, including installing dependencies. If you run into problems you might have to execute pip as admin, or if you have multiple Python versions installed explicitly use the pip of the compatible Python version.
