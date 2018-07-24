import os
from subprocess import call

rootdirs = ["D:\\gamedev\\ue4\\DA420X\\Plugins\\DungeonArchitect\\Source\\DungeonArchitectRuntime\\Private",
	"D:\\gamedev\\ue4\\DA420X\\Plugins\\DungeonArchitect\\Source\\DungeonArchitectHelpSystem\\Private",
	"D:\\gamedev\\ue4\\DA420X\\Plugins\\DungeonArchitect\\Source\\DungeonArchitectEditor\\Private"]

sedexprs = []
	
def stringify_path(path):
	return path.replace("\\", "/")

def stringify(text):
	return text.replace("\"", "\\\"").replace("/", "\\/")

def GatherReplacements(rootdir, dir, file):
	filePath = "%s\\%s" % (dir, file)
	if not filePath.endswith(".cpp"):
		return
		
	className = file[:-4]
	searchText = "#include \"%s.h\"" % className
	basePath = filePath[len(rootdir) + 1:-len(file)].replace("\\", "/")
	if len(basePath) == 0:
		return;
	
	replaceText = "#include \"%s%s.h\"" % (basePath, className)
	sedexpr = "s/%s/%s/g" % (stringify(searchText), stringify(replaceText))
	sedexprs.append(sedexpr)
	

def ProcessFile(rootdir, dir, file):
	ContainsInclude(rootdir, dir, file)
	
	className = file[:-4]
	#print "Processing: " + className

for rootdir in rootdirs:
	for dir, subdirs, files in os.walk(rootdir):
		for file in files:
			GatherReplacements(rootdir, dir, file)

sed_file = open("sed_rules.txt", "w")
#command = "sed -i \"%s\" %s" % (expr, stringify_path(filePath))

for expr in sedexprs:
	sed_file.write(expr + "\n")
	
sed_file.close()
