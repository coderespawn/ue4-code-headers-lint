import os
import glob
import re
import sys
import pathlib
from subprocess import call
from collections import namedtuple
import json
import atexit
from datetime import datetime

class bcolors:
    HEADER = '\033[95m'
    OKRED = '\033[91m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def PrintError(ErrorMessage):
    print(bcolors.BOLD + bcolors.FAIL + "Error: " + bcolors.ENDC + ErrorMessage)


def ReadJson(filename):
    with open(filename) as json_file:
        data = json.load(json_file)
    return data


def GetBaseConfig():
    script_path = os.path.dirname(os.path.realpath(__file__))
    config_path = "%s/config/base_config.json" % script_path
    return ReadJson(config_path)


def GetPluginConfig(PluginPath):
    ConfigPath = PluginPath / "Scripts/HeaderLint/header_lint.json"
    if not ConfigPath.exists():
        return {}

    data = ReadJson(ConfigPath)
    data = data or {}
    return data


def PrintUsage():
    print("Usage: %s <SolutionDir> <CurrentFileDir>" % os.path.basename(__file__))


def check_filenames(directory, max_length):
    long_filenames = []

    for root, dirs, files in os.walk(directory):
        # Ignore hidden folders
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), directory)
            if len(relative_path) > max_length:
                long_filenames.append(relative_path)

    return long_filenames


class DebugLogger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DebugLogger, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        script_dir = os.path.dirname(os.path.realpath(__file__))
        log_dir = os.path.join(script_dir, "log")
        os.makedirs(log_dir, exist_ok=True)  # Create log directory if it doesn't exist
        self.filename = os.path.join(log_dir, "header_lint_debug.log")
        self.file = open(self.filename, 'w', encoding='utf-8')  # 'w' mode overwrites the file
        atexit.register(self.close)
        self.log("Debug logging started")

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.file.write(f"[{timestamp}] {message}\n")
        self.file.flush()  # Ensure it's written immediately

    def close(self):
        if not self.file.closed:
            self.log("Debug logging ended")
            self.file.close()
            print(f"Debug information has been written to {self.filename}")


########################################################################
debug_logger = DebugLogger()
SolutionDir = pathlib.Path(sys.argv[1])

for file in SolutionDir.glob("*.uproject"):
    UPROJECT_FILE = file
    break

if not UPROJECT_FILE:
    print("Cannot find uproject file")
    sys.exit();

UProjectJson = ReadJson(UPROJECT_FILE)
ENGINE_VERSION = UProjectJson["EngineAssociation"]
print("Engine: " + ENGINE_VERSION)

CurrentFileDir = pathlib.Path(sys.argv[2])

PluginPath = CurrentFileDir
while PluginPath != PluginPath.parent:
    if PluginPath.parent.name == "GameFeatures" or PluginPath.parent.name == "Plugins":
        break
    PluginPath = PluginPath.parent

if not PluginPath.parent:
    PrintError("Cannot find plugin path")
    sys.exit();

print("Plugin: " + PluginPath.name)

if len(sys.argv) < 3:
    PrintUsage()
    sys.exit()

# grab the script config
BaseConfig = GetBaseConfig()
if not BaseConfig:
    PrintError("cannot find base config file. aborting..")
    sys.exit()

preferred_paths = BaseConfig.get("preferred_paths", [])

# grab the plugin config
PluginConfig = GetPluginConfig(PluginPath)
ScriptEnabled = PluginConfig.get("enabled", False)

if not ScriptEnabled:
    PrintError("Header lint is not enabled in this module")
    sys.exit()

if not ENGINE_VERSION in BaseConfig["engine_path"]:
    PrintError("Unsupported engine version: %s" % ENGINE_VERSION)
    sys.exit()

# Configuration
ENGINE_SOURCE = BaseConfig["engine_path"][ENGINE_VERSION]
COPYRIGHT_NOTICE = BaseConfig["copyright"]
WHITELIST_PATHS = PluginConfig.get("whitelist_includes", [])
IGNORE_FILES = PluginConfig.get("ignore_files", [])
###

if not COPYRIGHT_NOTICE:
    PrintError("copyright not provided in base configuration")
    sys.exit()

## Init the directory list
enginedirs = [
    "%s/Runtime" % ENGINE_SOURCE,
    "%s/Editor" % ENGINE_SOURCE]

ModuleList = []

if "plugin_modules" in PluginConfig:
    for ModuleName in PluginConfig["plugin_modules"]:
        ModuleList.append(PluginPath / "Source" / ModuleName)
else:
    for ModuleDir in PluginPath.glob("Source/*"):
        ModuleList.append(ModuleDir)

print("Modules: " + ", ".join([x.name for x in ModuleList]))

rootdirs = ModuleList
# for ModuleName in ModuleList:
#	rootdirs.append("%s/%s" % (PLUGIN_SOURCE, ModuleName))


FileInfo = namedtuple("FileInfo", "rootdir dir cname module_path")
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
    with open(path, 'r', encoding='utf-8-sig') as f:
        lines = f.read().splitlines()
    return lines


def writeFile(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write('%s\n' % line)


def stringify_path(path):
    return path.replace("\\", "/")


def stringify(text):
    return text.replace("\"", "\\\"").replace("/", "\\/")


def IsLineInclude(line):
    return line.startswith("#include ") and not line.endswith(".inl\"")


def IsLineCopyright(line):
    sline = line.strip()
    return sline.startswith("//$ Copyright")  # and sline.endswith("$//")


def IsCustomHeaderBlockComment(line):
    sline = line.strip()
    return sline.startswith("//!!")


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


# returns success, pch, includes[], custom_includes[], code[]
def ProcessSourceRawLines(rawLines, cname):
    code = []
    includes = []
    custom_includes = []
    pch = ""
    bFoundPCH = False

    # Make sure we have a line ending
    if len(rawLines) > 0 and len(rawLines[-1]) > 0:
        rawLines.append("")

    bCustomHeaderBlock = False;
    bProcessingHeader = True
    for rawLine in rawLines:

        if IsCustomHeaderBlockComment(rawLine):
            bCustomHeaderBlock = not bCustomHeaderBlock
            custom_includes.append(rawLine)
            continue

        if bCustomHeaderBlock:
            custom_includes.append(rawLine)

        if not bCustomHeaderBlock:
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

    Success = True
    if bCustomHeaderBlock:
        print("WARN: Malformed custom include block. %s.cpp" % cname)
        Success = False

    return Success, pch, includes, custom_includes, code


def ShouldIgnoreFile(first_line):
    return first_line.startswith('//~')


def ProcessSourceFile(info):
    filePath = "%s/%s/%s.cpp" % (info.rootdir, info.dir, info.cname)
    # print("Source:", info.cname)

    rawLines = readFile(filePath)

    if len(rawLines) > 0 and ShouldIgnoreFile(rawLines[0]):
        return False

    success, pch, base_includes, custom_includes, code = ProcessSourceRawLines(rawLines, info.cname)
    if not success:
        return False

    includes = []
    includes.append(ProcessInclude(pch)[0])
    includes.append("")
    includes.extend(ProcessIncludes(base_includes))
    includes.extend(custom_includes)

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


# returns success, includes[], custom_includes[], genheader, code[]
def ProcessHeaderRawLines(rawLines, cname):
    code = []
    includes = []
    custom_includes = []
    genheader = None

    # Make sure we have a line ending
    if len(rawLines) > 0 and len(rawLines[-1]) > 0:
        rawLines.append("")

    bCustomHeaderBlock = False;
    bProcessingHeader = True
    for rawLine in rawLines:
        if IsCustomHeaderBlockComment(rawLine):
            bCustomHeaderBlock = not bCustomHeaderBlock
            custom_includes.append(rawLine)
            continue

        if bCustomHeaderBlock:
            custom_includes.append(rawLine)

        if not bCustomHeaderBlock:
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

    Success = True
    if bCustomHeaderBlock:
        print("WARN: Malformed custom include block. %s.cpp" % cname)
        Success = False

    return Success, includes, custom_includes, genheader, code


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
    # print("Header:", info.cname)

    rawLines = readFile(filePath)
    if len(rawLines) > 0 and ShouldIgnoreFile(rawLines[0]):
        return False

    ValidateHeaderRawLines(rawLines, info.cname)
    success, base_includes, custom_includes, genheader, code = ProcessHeaderRawLines(rawLines, info.cname)

    if not success:
        return False

    includes = ProcessIncludes(base_includes)

    lines = []
    lines.append(COPYRIGHT_NOTICE)
    lines.append("")
    lines.append("#pragma once")
    lines.append("#include \"CoreMinimal.h\"")
    lines.extend(includes)
    lines.extend(custom_includes)
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


def LTrimFromSubStr(text, substr):
    index = text.find(substr)
    if index != -1:
        text = text[:index]
    if text.endswith("/"):
        text = text[:-1]
    return text.strip()

def score_path(path, preferred_paths):
    for i, preferred in enumerate(preferred_paths):
        if preferred in path:
            return len(preferred_paths) - i
    return 0


def GenerateFileList(rootdir, extension, fileList, engineFiles=False, preferred_paths=[]):
    for dir, subdirs, files in os.walk(rootdir):
        reldir = dir[len(rootdir) + 1:]
        reldir = reldir.replace("\\", "/")
        module_path = reldir
        if engineFiles:
            reldir = RTrimFromSubStr(reldir, "Public")
            reldir = RTrimFromSubStr(reldir, "Classes")
            reldir = RTrimFromSubStr(reldir, "Private")

            #module_path = LTrimFromSubStr(module_path, "Public")
            #module_path = LTrimFromSubStr(module_path, "Classes")
            #module_path = LTrimFromSubStr(module_path, "Private")
            module_path.strip()

            if reldir[0:1] == "/":
                reldir = reldir[:1]
            reldir = reldir.strip()

        if reldir.startswith("Microsoft"):
            continue

        for file in files:
            if not file.endswith(extension):
                continue

            fullPath = reldir.strip() + "/" + file
            if not engineFiles:
                if fullPath in IGNORE_FILES:
                    # print ("Ignoring file:", fullPath)
                    continue

                if file in IGNORE_FILES:
                    # print ("Ignoring file:", fullPath)
                    continue

            cname = file[:-len(extension) - 1]
            fileInfo = FileInfo(rootdir, reldir, cname, module_path)
            new_score = score_path(module_path, preferred_paths)

            if cname in fileList:
                existing_score = score_path(fileList[cname].module_path, preferred_paths)
                if new_score > existing_score:
                    fileList[cname] = fileInfo
            else:
                fileList[cname] = fileInfo


            #if True:  # not cname in fileList:
            #    if file.endswith(".%s" % extension):
            #        fileList[cname] = fileInfo


# Parse the engine code
# print("Paring engine code")
for enginedir in enginedirs:
    GenerateFileList(enginedir, "h", engineHeaders, True, preferred_paths)

print("Parsed engine code [%d Headers]" % len(engineHeaders))

externalHeaders = {}
if "external_game_modules" in PluginConfig:
    for GameModuleName in PluginConfig["external_game_modules"]:
        ExternalGameModPath = SolutionDir / "Source" / GameModuleName
        if ExternalGameModPath.exists():
            GenerateFileList(str(ExternalGameModPath), "h", externalHeaders, True)
        else:
            print("ERROR: Cannot find game module path: " + GameModuleName)

if "external_plugins" in PluginConfig:
    for ExternalPluginName in PluginConfig["external_plugins"]:
        ExternalPluginPath = SolutionDir / "Plugins" / "GameFeatures" / ExternalPluginName
        if not ExternalPluginPath.exists():
            ExternalPluginPath = SolutionDir / "Plugins" / ExternalPluginName

        if ExternalPluginPath.exists():
            GenerateFileList(str(ExternalPluginPath), "h", externalHeaders, True)
        else:
            print("ERROR: Cannot find plugin path: " + ExternalPluginName)

print("Parsed external code [%d Headers]" % len(externalHeaders))

engineHeaders.update(externalHeaders)

# Parse the plugin code
sourceList = {}
for rootdir in rootdirs:
    rootPublic = "%s/Public" % rootdir
    rootPrivate = "%s/Private" % rootdir
    GenerateFileList(rootPublic, "h", userHeaders)
    GenerateFileList(rootPrivate, "h", userHeaders)
    GenerateFileList(rootPublic, "cpp", sourceList)
    GenerateFileList(rootPrivate, "cpp", sourceList)
print("Parsed local code [%d Headers, %d Sources]" % (len(userHeaders), len(sourceList)))

NumSourceFilesModified = 0
NumHeaderFilesModified = 0

for key, info in sourceList.items():
    if ProcessSourceFile(info):
        NumSourceFilesModified = NumSourceFilesModified + 1

for key, info in userHeaders.items():
    if ProcessHeaderFile(info):
        NumHeaderFilesModified = NumHeaderFilesModified + 1

message = "Written " + bcolors.BOLD + bcolors.OKCYAN + "%d" + bcolors.ENDC + " Headers, " + bcolors.BOLD + bcolors.OKCYAN + "%d" + bcolors.ENDC + " Sources"
print(message % (NumHeaderFilesModified, NumSourceFilesModified))


# Check for long filenames
max_filename_length = 170
long_filenames = check_filenames(PluginPath, max_filename_length)

if long_filenames:
    PrintError(f"The following files in the '{PluginPath.name}' plugin have filenames greater than {max_filename_length} characters:")
    for filename in long_filenames:
        PrintError(filename)

