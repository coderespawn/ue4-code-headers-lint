import json
import os
import sys
import subprocess
from pathlib import Path


def load_config(config_path="config/base_config.json"):
    """Load the engine configuration file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        sys.exit(1)


def find_uproject_file(solution_path):
    """Find the .uproject file in the solution directory."""
    solution_dir = Path(solution_path)
    if solution_dir.is_file():
        solution_dir = solution_dir.parent

    uproject_files = list(solution_dir.glob("*.uproject"))

    if not uproject_files:
        print(f"Error: No .uproject file found in {solution_dir}")
        sys.exit(1)

    if len(uproject_files) > 1:
        print(f"Warning: Multiple .uproject files found. Using {uproject_files[0]}")

    return uproject_files[0]


def get_engine_version(uproject_path):
    """Extract engine version from .uproject file."""
    try:
        with open(uproject_path, 'r') as f:
            project_data = json.load(f)
            return project_data.get("EngineAssociation")
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"Error reading engine version from {uproject_path}: {e}")
        sys.exit(1)


def get_build_bat_path(engine_base_path):
    """Construct path to Build.bat."""
    engine_root = Path(engine_base_path).parent
    build_bat_path = engine_root / "Build" / "BatchFiles" / "Build.bat"

    print(f"Looking for Build.bat at: {build_bat_path}")

    if not build_bat_path.exists():
        print(f"Error: Build.bat not found at {build_bat_path}")
        sys.exit(1)

    return build_bat_path


def generate_project_files(solution_path):
    """Main function to generate project files."""
    # Load config
    config = load_config()

    # Find .uproject file
    uproject_path = find_uproject_file(solution_path)
    print(f"Found uproject at: {uproject_path}")

    # Get engine version
    engine_version = get_engine_version(uproject_path)
    print(f"Engine version: {engine_version}")

    # Get engine path from config
    if engine_version not in config["engine_path"]:
        print(f"Error: Engine version {engine_version} not found in config")
        sys.exit(1)

    engine_path = config["engine_path"][engine_version]

    # Get Build.bat path
    build_bat_path = get_build_bat_path(engine_path)

    # Construct command
    cmd = [
        str(build_bat_path),
        "-projectfiles",
        f"-project={uproject_path}",
        "-game",
        "-rocket",
        "-progress"
    ]

    print(f"Executing: {' '.join(cmd)}")

    try:
        # Start process with pipe for stdout and stderr
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )

        # Read output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.rstrip())

        # Get the return code
        return_code = process.poll()

        # Print any remaining stderr
        for line in process.stderr:
            print(line.rstrip(), file=sys.stderr)

        if return_code != 0:
            print(f"Process exited with code {return_code}")
            sys.exit(return_code)

    except subprocess.CalledProcessError as e:
        print(f"Error generating project files: {e}")
        print(e.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
        process.kill()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_project_files.py <solution_path>")
        sys.exit(1)

    generate_project_files(sys.argv[1])