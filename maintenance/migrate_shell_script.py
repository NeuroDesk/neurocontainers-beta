import os
import yaml
from subprocess import check_call

IGNORED_COMMANDS = [
    "printf '#!/bin/bash\\nls -la' > /usr/bin/ll",
    "chmod +x /usr/bin/ll",
    "mkdir -p /afm01 /afm02 /cvmfs /90days /30days /QRISdata /RDS /data /short /proc_temp /TMPDIR /nvme /neurodesktop-storage /local /gpfs1 /working /winmounts /state /tmp /autofs /cluster /local_mount /scratch /clusterdata /nvmescratch",
]


def str_presenter(dumper, data):
    if data.count("\n") > 0:
        data = "\n".join(
            [line.rstrip() for line in data.splitlines()]
        )  # Remove any trailing spaces, then put it back together again
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, str_presenter)
yaml.representer.SafeRepresenter.add_representer(str, str_presenter)


def read_json_file(file_path):
    import json

    with open(file_path, "r") as f:
        return json.load(f)


def write_yaml_file(file_path, data):
    with open(file_path, "w") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
            default_flow_style=False,
            width=10000,
        )


def migrate(data):
    ret = {
        "name": data["name"],
        "version": data["version"],
        "architectures": ["x86_64"],
        "build": {
            "kind": "neurodocker",
            "base-image": data["base_image"],
            "pkg-manager": data["pkg_manager"],
            "directives": [],
        },
        "deploy": {},
        "readme": "",
    }

    def add_directive(directive):
        ret["build"]["directives"].append(directive)

    def add_deploy_path(path):
        if "path" not in ret["deploy"]:
            ret["deploy"]["path"] = []
        ret["deploy"]["path"].append(path)

    def add_deploy_bin(bin):
        if "bin" not in ret["deploy"]:
            ret["deploy"]["bins"] = []
        ret["deploy"]["bins"].append(bin)

    def add_file(filename, contents):
        if "files" not in ret:
            ret["files"] = []
        ret["files"].append({"name": filename, "contents": contents})

    for arg in data["args"]:
        if "run" in arg:
            cmd = arg["run"].strip()

            if cmd in IGNORED_COMMANDS:
                continue

            if " && " in cmd:
                add_directive({"run": [s.rstrip() for s in cmd.split(" && ")]})
            else:
                add_directive({"run": [cmd]})
        elif "install" in arg:
            add_directive({"install": arg["install"]})
        elif "workdir" in arg:
            add_directive({"workdir": arg["workdir"]})
        elif "pkg" in arg:
            add_directive(
                {
                    "template": {
                        "name": arg["pkg"],
                        **arg["args"],
                    }
                }
            )
        elif "user" in arg:
            add_directive({"user": arg["user"]})
        elif "entrypoint" in arg:
            add_directive({"entrypoint": arg["entrypoint"]})
        elif "copy-from" in arg:
            raise NotImplementedError("copy-from is not supported")
        elif "env" in arg:
            filtered_env = {}
            for key in arg["env"]:
                if key == "DEPLOY_PATH":
                    for path in arg["env"]["DEPLOY_PATH"].split(":"):
                        add_deploy_path(path)
                elif key == "DEPLOY_BINS":
                    for bin in arg["env"]["DEPLOY_BINS"].split(":"):
                        add_deploy_bin(bin)
                else:
                    filtered_env[key] = arg["env"][key]
            if len(filtered_env) > 0:
                add_directive({"environment": filtered_env})
        elif "copy" in arg:
            target = arg["copy"]
            filename = arg["filename"]
            contents = None
            if "contents" in arg and arg["contents"] is not None:
                contents = arg["contents"].strip()
            if target == "/README.md":
                ret["readme"] = (
                    contents.replace("toolVersion", "{{ context.version }}")
                    .replace(ret["version"], "{{ context.version }}")
                    .replace("\\n", "\n")
                )
            elif contents == None:
                add_directive({"copy": [filename, target]})
            else:
                add_file(filename, contents)
                add_directive({"copy": filename + " " + target})
        else:
            print(arg)
            raise NotImplementedError("Unsupported argument")

    return ret


def main(args):
    json_filename = args[0]
    output_filename = args[1]

    json_data = read_json_file(json_filename)

    migrated_data = migrate(json_data)

    if not os.path.exists(os.path.dirname(output_filename)):
        os.makedirs(os.path.dirname(output_filename))

    write_yaml_file(output_filename, migrated_data)

    if os.getenv("TEST") == "1":
        check_call(["python3", "build.py", "--recreate", output_filename, "build"])


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
