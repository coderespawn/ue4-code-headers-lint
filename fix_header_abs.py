import os
import re
from subprocess import call
from collections import namedtuple

FileInfo = namedtuple("FileInfo", "rootdir dir cname")
headerList = {}

code_copyright = "//$ Copyright 2015-18, Code Respawn Technologies Pvt Ltd - All Rights Reserved $//"

rootdirs = ["D:\\gamedev\\ue4\\DA420X\\Plugins\\DungeonArchitect\\Source\\DungeonArchitectRuntime",
	"D:\\gamedev\\ue4\\DA420X\\Plugins\\DungeonArchitect\\Source\\DungeonArchitectHelpSystem",
	"D:\\gamedev\\ue4\\DA420X\\Plugins\\DungeonArchitect\\Source\\DungeonArchitectEditor"]


def ProcessInclude(include):
	pattern_dir = '#include \".*/(.*).h\"'
	pattern_simple = '#include \"(.*).h\"'
	
	m = re.search(pattern_dir, include)
	if not m:
		m = re.search(pattern_simple, include)
		
	if not m:
		return include, False
		
	cname = m.group(1)
	if not cname in headerList:
		return include, False
	
	# We found a class include that is part of the project
	info = headerList[cname]
	if len(info.dir) == 0:
		return include, True

	# Rewrite with the absolute path
	include = '#include \"%s/%s.h\"' % (info.dir, info.cname)
	
	return include, True
	
def ProcessIncludes(base_includes):
	user_includes = []
	engine_includes = []
	
	for base_include in base_includes:
		include, bUserCode = ProcessInclude(base_include)
		if bUserCode:
			user_includes.append(include)
		else:
			engine_includes.append(include)
			
	user_includes.sort()
	engine_includes.sort()
	
	result = []
	
	if (len(user_includes) > 0):
		result.extend(user_includes)
		
	if (len(engine_includes) > 0):
		if (len(result) > 0):
			result.append("")
		result.extend(engine_includes)
	
	return result
	
def readFile(path):
	lines = []
	with open(path) as f:
		lines = f.read().splitlines()	
	return lines

def writeFile(path, lines):
	with open(path, 'w') as f:
		for line in lines:
			f.write('%s\n' % line)
	
def stringify_path(path):
	return path.replace("\\", "/")

def stringify(text):
	return text.replace("\"", "\\\"").replace("/", "\\/")

def IsLineInclude(line):
	return line.startswith("#include ")
	
def IsLineCopyright(line):
	sline = line.strip()
	return sline.startswith("//$ Copyright") # and sline.endswith("$//")
	
def IsLineEmpty(line):
	return len(line.strip()) == 0
	
# returns pch, includes[], code[]
def ProcessSourceRawLines(rawLines):
	# Make sure we have a line ending
	if len(rawLines[-1]) > 0:
		rawLines.append("")
	
	code = []
	includes = []
	pch = ""
	bFoundPCH = False
	
	bProcessingHeader = True
	for rawLine in rawLines:
		if bProcessingHeader:
			if IsLineEmpty(rawLine):
				continue
			elif IsLineCopyright(rawLine):
				continue
			elif IsLineInclude(rawLine):
				if not bFoundPCH:
					bFoundPCH = True
					pch = rawLine
				else:
					includes.append(rawLine)
					
			else:
				bProcessingHeader = False;
		
		if not bProcessingHeader:
			code.append(rawLine)
	return pch, includes, code
	
def ProcessSourceFile(info):
	filePath = "%s\\%s\\%s.cpp" % (info.rootdir, info.dir, info.cname)
	print "Source:", info.cname
	
	pch, base_includes, code = ProcessSourceRawLines(readFile(filePath))
	
	includes = []
	includes.append(ProcessInclude(pch)[0])
	includes.append("")
	includes.extend(ProcessIncludes(base_includes))
	
	lines = []
	lines.append(code_copyright)
	lines.append("")
	lines.extend(includes)
	lines.append("")
	lines.extend(code)
	
	
	writeFile(filePath, lines)
	return True

# returns includes[], genheader, code[]
def ProcessHeaderRawLines(rawLines):
	# Make sure we have a line ending
	if len(rawLines[-1]) > 0:
		rawLines.append("")
	
	code = []
	includes = []
	genheader = None
	
	bProcessingHeader = True
	for rawLine in rawLines:
		if bProcessingHeader:
			if IsLineEmpty(rawLine):
				continue
			elif IsLineCopyright(rawLine):
				continue
			elif rawLine.strip() == '#pragma once':
				continue
			elif rawLine.strip() == '#include \"CoreMinimal.h\"':
				continue
			elif IsLineInclude(rawLine):
				if rawLine.strip().endswith(".generated.h\""):
					genheader = rawLine
				else:
					includes.append(rawLine)
			else:
				bProcessingHeader = False;
		
		if not bProcessingHeader:
			code.append(rawLine)
			
	return includes, genheader, code
	
	
def ProcessHeaderFile(info):
	filePath = "%s\\%s\\%s.h" % (info.rootdir, info.dir, info.cname)
	print "Header:", info.cname
	
	base_includes, genheader, code = ProcessHeaderRawLines(readFile(filePath))
	
	includes = ProcessIncludes(base_includes)
	
	lines = []
	lines.append(code_copyright)
	lines.append("")
	lines.append("#pragma once")
	lines.append("#include \"CoreMinimal.h\"")
	lines.extend(includes)
	if genheader:
		lines.append(genheader)
		
	lines.append("")
	lines.extend(code)
	
	
	writeFile(filePath, lines)
	return True
	
def GenerateFileList(rootdir, extension, fileList):
	for dir, subdirs, files in os.walk(rootdir):
		for file in files:
			if not file.endswith(extension):
				continue
			reldir = dir[len(rootdir)+1:]
			reldir = reldir.replace("\\", "/")
			cname = file[:-len(extension)-1]
			fileInfo = FileInfo(rootdir, reldir, cname)
			if file.endswith(".%s" % extension):
				fileList[cname] = fileInfo

	
sourceList = {}
for rootdir in rootdirs:
	rootPublic = "%s\\Public" % rootdir
	rootPrivate = "%s\\Private" % rootdir
	GenerateFileList(rootPublic, "h", headerList)
	GenerateFileList(rootPrivate, "h", headerList)
	GenerateFileList(rootPublic, "cpp", sourceList)
	GenerateFileList(rootPrivate, "cpp", sourceList)

	
for key, info in sourceList.items():
	ProcessSourceFile(info)

for key, info in headerList.items():
	ProcessHeaderFile(info)
