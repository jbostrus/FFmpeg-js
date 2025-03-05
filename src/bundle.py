import os, base64, requests
from jsmin import jsmin
from concurrent.futures import ProcessPoolExecutor


DEBUG = False


SRC_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(os.path.dirname(SRC_DIR), "ffmpeg.wasm")
OUT_DIR = os.path.join(os.path.dirname(SRC_DIR), "out")

FFMPEG_CORE_WASM = os.path.join(
	FFMPEG_DIR,
	"packages", "core", "dist", "esm", "ffmpeg-core.wasm"
)
FFMPEG_CORE_JS = os.path.join(
	FFMPEG_DIR,
	"packages", "core", "dist", "esm", "ffmpeg-core.js"
)
TEMPLATE = os.path.join(
	SRC_DIR, "_template.js"
)

def preProcess(js, corejsB64, corewasmB64):
	while -1 != (loc:=js.find("\n#!")):
		content = ""
		next_nl = js[loc+3:].find("\n")
		assert next_nl != -1, "All commands must be done with a newline following!"
		after = js[loc+3 + next_nl: ]


		if js[loc+3:].startswith("include"):
			f = open(os.path.join(SRC_DIR, js[loc:].split('"')[1]), "r")
			content = f.read()
			f.close()
		elif js[loc+3:].startswith("b64_include"):
			after_command = js[loc+len("\n#!b64_include "): ].split("\n")[0]
			name, file = after_command.split(", ")
			content = f"const {name} = '"

			f = open(os.path.join(SRC_DIR, file.split('"')[1]), "r")
			content += base64.b64encode(
				preProcess(f.read(), corejsB64, corewasmB64).encode("utf-8")
				).decode("ascii")
			content += "';"

			f.close()
		else:
			content = f'/* UNKNOWN COMMAND "{js[loc+3:].split("\n")[0]}" */'
		js = js[:loc] + content + after
	js = js.replace(r"{{base64_corejs}}", corejsB64).replace(r"{{base64_corewasm}}", corewasmB64)
	if not DEBUG:
		js = jsmin(js)
	return js

def createBundle(corejsB64, corewasmB64, outName):
	f = open(TEMPLATE, "r")
	js = f.read()
	f.close()
	
	js = preProcess(js, corejsB64, corewasmB64)

	f = open(outName, "w")
	f.write(js)
	f.close()

def generateFromLocal():
	f = open(FFMPEG_CORE_WASM, "rb")
	wasm = f.read()
	f.close()
	f = open(FFMPEG_CORE_JS, "rb")
	js = f.read()
	f.close()

	createBundle(
		base64.b64encode(js).decode("ascii"),
		base64.b64encode(wasm).decode("ascii"),
		os.path.join(os.path.dirname(SRC_DIR), "out", "latest.bundle.js")
	)
def generateFromVersion(version):
	js = requests.get(f"https://unpkg.com/@ffmpeg/core@{version}/dist/esm/ffmpeg-core.js")
	wasm = requests.get(f"https://unpkg.com/@ffmpeg/core@{version}/dist/esm/ffmpeg-core.wasm")

	if js.status_code != 200:
		print(f"Failed to get {version} due to {js.status_code} status code in {js.url}")
		return
	if wasm.status_code != 200:
		print(f"Failed to get {version} due to {wasm.status_code} status code in {wasm.url}")
		return

	createBundle(
		base64.b64encode(js.content).decode("ascii"),
		base64.b64encode(wasm.content).decode("ascii"),
		os.path.join(os.path.dirname(SRC_DIR), "out", version + ".bundle.js")
	)

def onlineGen(v):
	try:
		generateFromVersion(v)
		print(f"Online bundle generated for {v}")
	except Exception as e:
		print(f"Error: Unable to generate bundle from online version {v}: {e}")

def main():
	try:
		generateFromLocal()
		print("Local bundle generated!")
	except Exception as e:
		print(f"Error: Unable to generate bundle from local: {e}")
	with ProcessPoolExecutor(max_workers=8) as e:
		for v in requests.get("https://api.cdnjs.com/libraries/ffmpeg?fields=versions").json()["versions"]:
			# This wont work with older versions
			if v.split(".")[1] != "12":
				continue
			e.submit(onlineGen, v)

if __name__ == "__main__":
	main()

