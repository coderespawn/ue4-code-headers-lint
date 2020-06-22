import os
import re
import sys
from subprocess import call
from collections import namedtuple
import json


def ReadJson(filename):
	with open(filename) as json_file:  
		data = json.load(json_file)
	return data

def GetBaseConfig():
	script_path = os.path.dirname(os.path.realpath(__file__))
	config_path = "%s/config/base_config.json" % script_path
	return ReadJson(config_path)
	
	
def GetPluginConfig():
	return ReadJson(sys.argv[1])

def PrintUsage():
	print("Usage: %s <PluginConfigFile.json> <PluginSourceDir>" % os.path.basename(__file__))
	
	
if len(sys.argv) < 3:
	PrintUsage()
	sys.exit()

# grab the script config
BaseConfig = GetBaseConfig()
if not BaseConfig:
	print("cannot find base config file. aborting..")
	sys.exit()

#grab the plugin config
PluginConfig = GetPluginConfig()
if not PluginConfig:
	print("Invalid plugin config file")
	PrintUsage()
	sys.exit()

ENGINE_VER = PluginConfig["engine_version"]
if not ENGINE_VER:
	print("Missing engine_version in project config")
	sys.exit()
	
if not ENGINE_VER in BaseConfig["engine_path"]:
	print("Unsupported engine version: %s" % ENGINE_VER)
	sys.exit()


# Configuration
PLUGIN_SOURCE = sys.argv[2]
ENGINE_SOURCE = BaseConfig["engine_path"][ENGINE_VER]
COPYRIGHT_NOTICE = BaseConfig["copyright"]
WHITELIST_PATHS = PluginConfig.get("whitelist_includes", [])
IGNORE_FILES = PluginConfig.get("ignore_files", [])
###

if not PLUGIN_SOURCE:
	print("plugin_source_dir not provided in args")
	sys.exit()
	
if not COPYRIGHT_NOTICE:
	print("copyright not provided in base configuration")
	sys.exit()

	
## Init the directory list
enginedirs = [
	"%s/Runtime" % ENGINE_SOURCE,
	"%s/Editor" % ENGINE_SOURCE]

rootdirs = []
for ModuleName in PluginConfig["plugin_modules"]:
	rootdirs.append("%s/%s" % (PLUGIN_SOURCE, ModuleName))


FileInfo = namedtuple("FileInfo", "rootdir dir cname")
userHeaders = {}
engineHeaders = {}


def IsWhitelisted(include):
	pattern = '#include \"(.*)\"'
	m = re.search(pattern, include)
	if m:
		path = m.group(1)
		if path in WHITELIST_PATHS:
			return True
	return False
	
def ProcessInclude(include):
	if IsWhitelisted(include):
		return include, False
	
	pattern_dir = '#include \".*/(.*).h\"'
	pattern_simple = '#include \"(.*).h\"'
	
	m = re.search(pattern_dir, include)
	if not m:
		m = re.search(pattern_simple, include)
		
	if not m:
		return include, False
		
	cname = m.group(1)
	
	if not cname in userHeaders:
		# This is probably an engine header. Try to fix it from the engine header metadata
		if cname in engineHeaders:
			info = engineHeaders[cname]
			if len(info.dir) > 0:
				include = '#include \"%s/%s.h\"' % (info.dir, info.cname)
		return include, False
	
	# We found a class include that is part of the project
	info = userHeaders[cname]
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
	with open(path, 'r') as f:
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

def IsComment(line):
	return line.strip().startswith("//")
	
def IsLineEmpty(line):
	return len(line.strip()) == 0
	
def AreLinesEqual(linesA, linesB):
	if len(linesA) != len(linesB):
		return False
	
	for idx, lineA in enumerate(linesA):
		lineB = linesB[idx]
		if lineA != lineB:
			return False
			
	return True
	
# returns pch, includes[], code[]
def ProcessSourceRawLines(rawLines, cname):
	code = []
	includes = []
	pch = ""
	bFoundPCH = False
	
	# Make sure we have a line ending
	if len(rawLines) > 0 and len(rawLines[-1]) > 0:
		rawLines.append("")
	
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
			if IsLineInclude(rawLine):
				print("WARN: Include not processed: %s.cpp" % cname)
			
	return pch, includes, code
	
def ProcessSourceFile(info):
	filePath = "%s/%s/%s.cpp" % (info.rootdir, info.dir, info.cname)
	#print("Source:", info.cname)
	
	rawLines = readFile(filePath)
	pch, base_includes, code = ProcessSourceRawLines(rawLines, info.cname)
	
	includes = []
	includes.append(ProcessInclude(pch)[0])
	includes.append("")
	includes.extend(ProcessIncludes(base_includes))
	
	lines = []
	lines.append(COPYRIGHT_NOTICE)
	lines.append("")
	lines.extend(includes)
	lines.append("")
	lines.extend(code)
	
	if AreLinesEqual(rawLines, lines):
		return False
	
	writeFile(filePath, lines)
	return True

# returns includes[], genheader, code[]
def ProcessHeaderRawLines(rawLines, cname):
	code = []
	includes = []
	genheader = None
	
	# Make sure we have a line ending
	if len(rawLines) > 0 and len(rawLines[-1]) > 0:
		rawLines.append("")
	
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
			if IsLineInclude(rawLine):
				print("WARN: Include not processed: %s.h" % cname)
			
	return includes, genheader, code


def StripComment(line):
	index = line.find('//')
	if index != -1:
		line = line[:index]
	return line

def ValidateHeaderRawLines(rawLines, filename):
	# Check if blueprint properties have category defined
	pattern = '(UPROPERTY|UFUNCTION)\((.*Blueprint.*)\)'
	for i, rawLine in enumerate(rawLines):
		line = StripComment(rawLine)
		m = re.search(pattern, line)
		if m:
			params = m.group(2)
			if params.lower().find('category') == -1:
				print("Blueprint access doesn't have a category. [{}.h:{}] {}".format(filename, i + 1, line))

	
def ProcessHeaderFile(info):
	filePath = "%s/%s/%s.h" % (info.rootdir, info.dir, info.cname)
	#print("Header:", info.cname)
	
	rawLines = readFile(filePath)
	ValidateHeaderRawLines(rawLines, info.cname)
	base_includes, genheader, code = ProcessHeaderRawLines(rawLines, info.cname)
	
	includes = ProcessIncludes(base_includes)
	
	lines = []
	lines.append(COPYRIGHT_NOTICE)
	lines.append("")
	lines.append("#pragma once")
	lines.append("#include \"CoreMinimal.h\"")
	lines.extend(includes)
	if genheader:
		lines.append(genheader)
		
	lines.append("")
	lines.extend(code)
	
	if AreLinesEqual(rawLines, lines):
		return False
	
	writeFile(filePath, lines)
	return True
	
def RTrimFromSubStr(text, substr):
	index = text.rfind(substr)
	if index != -1:
		text = text[index + len(substr):]
	if text[0:1] == "/":
		text = text[1:]
	return text
	
def GenerateFileList(rootdir, extension, fileList, engineFiles = False):
	for dir, subdirs, files in os.walk(rootdir):
		reldir = dir[len(rootdir)+1:]
		reldir = reldir.replace("\\", "/")
		if engineFiles:
			reldir = RTrimFromSubStr(reldir, "Public")
			reldir = RTrimFromSubStr(reldir, "Classes")
			reldir = RTrimFromSubStr(reldir, "Private")
			if reldir[0:1] == "/":
				reldir = reldir[:1]
			reldir = reldir.strip()
		
		if reldir.startswith("Microsoft"):
			continue
		
		for file in files:
			if not file.endswith(extension):
				continue

			if not engineFiles:
				fullPath = reldir.strip() + "/" + file
				if fullPath in IGNORE_FILES:
					#print ("Ignoring file:", fullPath)
					continue

			cname = file[:-len(extension)-1]
			fileInfo = FileInfo(rootdir, reldir, cname)
			if file.endswith(".%s" % extension):
				fileList[cname] = fileInfo

#Parse the engine code
print("Paring engine code")
for enginedir in enginedirs:
	GenerateFileList(enginedir, "h", engineHeaders, True)

print("Parsed %d Headers" % len(engineHeaders))


#Parse the plugin code				
print("Parsing plugin code")
sourceList = {}
for rootdir in rootdirs:
	rootPublic = "%s/Public" % rootdir
	rootPrivate = "%s/Private" % rootdir
	GenerateFileList(rootPublic, "h", userHeaders)
	GenerateFileList(rootPrivate, "h", userHeaders)
	GenerateFileList(rootPublic, "cpp", sourceList)
	GenerateFileList(rootPrivate, "cpp", sourceList)
print("Parsed %d Headers, %d Sources" % (len(userHeaders), len(sourceList)))

NumSourceFilesModified = 0
NumHeaderFilesModified = 0

for key, info in sourceList.items():
	if ProcessSourceFile(info):
		NumSourceFilesModified = NumSourceFilesModified + 1

for key, info in userHeaders.items():
	if ProcessHeaderFile(info):
		NumHeaderFilesModified = NumHeaderFilesModified + 1

print("Written %d Headers, %d Sources" % (NumHeaderFilesModified, NumSourceFilesModified))
